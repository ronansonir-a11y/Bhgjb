package dev.arena.dota2port;

import android.content.Context;
import android.os.Build;
import android.os.Environment;
import android.util.Log;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Phone-only game-content installer. Streams a ZIP from a URL supplied by the
 * user (their own legally obtained copy of "dota 2 beta", a private cloud link,
 * etc.) directly into /sdcard/Dota2/ without caching a 30 GB archive.
 *
 * IMPORTANT: this class never downloads Valve files itself and no Valve files
 * are shipped in the APK or in GitHub Releases. DepotDownloader needs the
 * user's own Steam account; see docs/07-MOBILE-ONLY.md.
 */
public final class ContentInstaller {
    private static final String TAG = "Dota2Content";

    public interface Progress {
        void onStage(String label, int percent, String detail);
        void onDone(boolean ok, String message);
    }

    private ContentInstaller() {}

    public static File gameRoot() {
        return new File(Environment.getExternalStorageDirectory(), "Dota2");
    }

    public static boolean hasAllFilesAccess() {
        if (Build.VERSION.SDK_INT < 30) return true; // legacy external storage, targetSdk 28
        return Environment.isExternalStorageManager();
    }

    public static void install(final String url, final Progress cb, final AtomicBoolean cancel) {
        new Thread(() -> {
            File root = gameRoot();
            try {
                if (!root.exists() && !root.mkdirs())
                    throw new Exception("Не удалось создать " + root + ". Дайте доступ к файлам.");
                HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                c.setInstanceFollowRedirects(true);
                c.setConnectTimeout(25000);
                c.setReadTimeout(45000);
                c.setRequestProperty("User-Agent", "Bhgjb-Dota2Mobile/1.0");
                int code = c.getResponseCode();
                if (code < 200 || code >= 300) throw new Exception("HTTP " + code);
                long total = c.getContentLengthLong();
                cb.onStage("Загрузка контента", 0, total > 0 ? human(total) : "?");
                InputStream raw = c.getInputStream();
                // CountingStream lets us show progress while ZipInputStream consumes it.
                CountingInputStream cis = new CountingInputStream(new BufferedInputStream(raw, 65536));
                ZipInputStream zis = new ZipInputStream(cis);
                String rootPath = root.getCanonicalPath() + File.separator;
                long[] last = {0};
                ZipEntry e;
                int files = 0;
                byte[] buf = new byte[65536];
                while ((e = zis.getNextEntry()) != null) {
                    if (cancel.get()) break;
                    String name = e.getName();
                    if (name.startsWith("__MACOSX") || name.contains("..")) { zis.closeEntry(); continue; }
                    File target = new File(root, name);
                    if (!target.getCanonicalPath().startsWith(rootPath))
                        throw new Exception("zip-slip blocked: " + name);
                    if (e.isDirectory()) {
                        if (!target.exists() && !target.mkdirs()) throw new Exception("mkdir " + target);
                    } else {
                        File parent = target.getParentFile();
                        if (parent != null && !parent.exists() && !parent.mkdirs())
                            throw new Exception("mkdir " + parent);
                        OutputStream os = new FileOutputStream(target);
                        int n;
                        try {
                            while ((n = zis.read(buf)) > 0) {
                                os.write(buf, 0, n);
                                if (cis.count - last[0] > 262144) {
                                    last[0] = cis.count;
                                    int pct = total > 0 ? (int) Math.min(99, cis.count * 100 / total) : 0;
                                    cb.onStage("Загрузка контента", pct, human(cis.count) + " · файлов: " + files);
                                }
                            }
                        } finally { os.close(); }
                        files++;
                    }
                    zis.closeEntry();
                }
                zis.close();
                c.disconnect();
                if (cancel.get()) { cb.onDone(false, "Отменено"); return; }
                cb.onStage("Готово", 100, "Файлов: " + files);
                cb.onDone(true, "Распаковано файлов: " + files + "\n" + root.getAbsolutePath() +
                        "\nПроверьте game/bin/win64/dota2.exe и game/dota/pak01_*.vpk");
            } catch (Exception ex) {
                Log.e(TAG, "content install failed", ex);
                cb.onDone(false, "Ошибка: " + ex.getMessage());
            }
        }, "dota2-content").start();
    }

    private static String human(long b) {
        if (b < 1024 * 1024) return String.format(Locale.US, "%.0f КиБ", b / 1024.0);
        return String.format(Locale.US, "%.1f МиБ", b / 1048576.0);
    }

    private static final class CountingInputStream extends InputStream {
        private final InputStream in;
        long count;
        CountingInputStream(InputStream in) { this.in = in; }
        @Override public int read() throws java.io.IOException {
            int v = in.read(); if (v >= 0) count++; return v;
        }
        @Override public int read(byte[] b, int off, int len) throws java.io.IOException {
            int n = in.read(b, off, len); if (n > 0) count += n; return n;
        }
        @Override public void close() throws java.io.IOException { in.close(); }
    }
}
