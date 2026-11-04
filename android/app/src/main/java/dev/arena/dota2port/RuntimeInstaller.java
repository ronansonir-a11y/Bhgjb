package dev.arena.dota2port;

import android.content.Context;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Phone-only runtime installer: downloads the two plain ZIPs published as
 * Release assets, verifies SHA-256, and unpacks them into app-private files.
 *
 * No PC, no ADB, no root. All sources are third-party open-source components
 * (Wine/Box64/Turnip/Vortek/Goldberg) -- never Valve files.
 */
public final class RuntimeInstaller {
    private static final String TAG = "Dota2Installer";
    private static final String SOURCES_ASSET = "dota2/runtime-sources.json";

    public interface Progress {
        void onStage(String label, int percent, String detail);
        void onDone(boolean ok, String message);
    }

    private static final class Asset {
        String id, name, url, sha256;
        long bytes;
    }

    private RuntimeInstaller() {}

    public static File runtimeDir(Context ctx) {
        return new File(ctx.getFilesDir(), "runtime");
    }

    public static File installedMarker(Context ctx) {
        return new File(runtimeDir(ctx), "installed.json");
    }

    public static void install(final Context ctx, final Progress cb, final AtomicBoolean cancel) {
        new Thread(() -> {
            try {
                doInstall(ctx, cb, cancel);
            } catch (Throwable t) {
                Log.e(TAG, "install failed", t);
                cb.onDone(false, "Ошибка: " + t.getMessage());
            }
        }, "dota2-install").start();
    }

    private static void doInstall(Context ctx, Progress cb, AtomicBoolean cancel) throws Exception {
        File root = runtimeDir(ctx);
        File downloads = new File(ctx.getFilesDir(), "downloads");
        if (!root.exists() && !root.mkdirs()) throw new IOException("cannot create runtime dir");
        if (!downloads.exists() && !downloads.mkdirs()) throw new IOException("cannot create download dir");

        JSONObject src = new JSONObject(Assets.readText(ctx, SOURCES_ASSET));
        String manifestUrl = src.optString("manifestUrl", "");
        List<Asset> assets = new ArrayList<>();

        JSONObject remote = null;
        if (manifestUrl.length() > 0) {
            try {
                cb.onStage("Манифест релиза", 0, manifestUrl);
                remote = new JSONObject(httpText(manifestUrl, cancel));
            } catch (Exception e) {
                Log.w(TAG, "no remote manifest, using bundled URLs: " + e);
            }
        }
        JSONArray list = remote != null ? remote.optJSONArray("assets")
                                        : src.getJSONArray("assets");
        if (list == null) list = src.getJSONArray("assets");
        for (int i = 0; i < list.length(); i++) {
            JSONObject o = list.getJSONObject(i);
            Asset a = new Asset();
            a.id = o.optString("id", "asset" + i);
            a.name = o.optString("name", a.id + ".zip");
            a.url = o.getString("url");
            a.sha256 = o.optString("sha256", "");
            a.bytes = o.optLong("bytes", 0);
            assets.add(a);
        }
        if (assets.isEmpty()) throw new IOException("empty runtime manifest");

        long total = 0;
        for (Asset a : assets) total += a.bytes;
        long done = 0;

        for (Asset a : assets) {
            if (cancel.get()) { cb.onDone(false, "Отменено"); return; }
            File part = new File(downloads, a.name + ".part");
            File zip = new File(downloads, a.name);
            if (!zip.exists() || a.bytes > 0 && zip.length() != a.bytes) {
                final long doneBefore = done;
                final long totalFinal = total;
                cb.onStage("Загрузка: " + a.name, pct(done, total), "0 / " + human(a.bytes));
                download(a.url, part, cancel, (n, len) -> {
                    long cur = doneBefore + n;
                    long tot = totalFinal > 0 ? totalFinal : Math.max(len, 1);
                    cb.onStage("Загрузка: " + a.name, (int) (cur * 100 / tot),
                            human(n) + " / " + human(len > 0 ? len : a.bytes));
                });
                if (cancel.get()) { part.delete(); cb.onDone(false, "Отменено"); return; }
                if (zip.exists() && !zip.delete()) Log.w(TAG, "cannot remove old zip");
                if (!part.renameTo(zip)) throw new IOException("rename failed: " + part);
            }
            if (a.sha256 != null && a.sha256.length() >= 16) {
                cb.onStage("Проверка SHA-256", pct(done, total), a.name);
                String actual = sha256(zip);
                if (!actual.equalsIgnoreCase(a.sha256)) {
                    zip.delete();
                    throw new IOException("SHA-256 mismatch for " + a.name);
                }
            }
            done += a.bytes > 0 ? a.bytes : zip.length();
            cb.onStage("Распаковка: " + a.name, pct(done, total), "в память приложения");
            int files = unzip(zip, root, cancel);
            Log.i(TAG, a.name + " -> " + files + " files");
        }

        JSONObject marker = new JSONObject();
        marker.put("installed", true);
        marker.put("components", new JSONArray(assetIds(assets)));
        marker.put("at", System.currentTimeMillis());
        FileOutputStream fos = new FileOutputStream(installedMarker(ctx));
        fos.write(marker.toString(2).getBytes(StandardCharsets.UTF_8));
        fos.close();
        cb.onStage("Готово", 100, "Рантайм установлен");
        cb.onDone(true, "Установлено компонентов: " + assets.size() + "\n" +
                "Путь: " + root.getAbsolutePath());
    }

    private static List<String> assetIds(List<Asset> a) {
        List<String> r = new ArrayList<>();
        for (Asset x : a) r.add(x.id);
        return r;
    }

    private static int pct(long done, long total) {
        if (total <= 0) return 0;
        return (int) Math.min(99, done * 100 / total);
    }

    private static String human(long b) {
        if (b <= 0) return "?";
        if (b < 1024) return b + " B";
        if (b < 1024 * 1024) return String.format(Locale.US, "%.0f КиБ", b / 1024.0);
        return String.format(Locale.US, "%.1f МиБ", b / 1048576.0);
    }

    private interface BytesCb { void onBytes(long soFar, long total); }

    private static void download(String url, File out, AtomicBoolean cancel, BytesCb cb) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setInstanceFollowRedirects(true);
        c.setConnectTimeout(25000);
        c.setReadTimeout(45000);
        c.setRequestProperty("User-Agent", "Bhgjb-Dota2Mobile/1.0");
        int code = c.getResponseCode();
        if (code < 200 || code >= 300) {
            c.disconnect();
            throw new IOException("HTTP " + code + " for " + url);
        }
        long total = c.getContentLengthLong();
        InputStream in = new BufferedInputStream(c.getInputStream(), 65536);
        OutputStream os = new FileOutputStream(out);
        try {
            byte[] buf = new byte[65536];
            long soFar = 0;
            int n;
            long lastReport = 0;
            while ((n = in.read(buf)) > 0) {
                if (cancel.get()) break;
                os.write(buf, 0, n);
                soFar += n;
                if (soFar - lastReport > 262144 || total > 0 && soFar == total) {
                    lastReport = soFar;
                    cb.onBytes(soFar, total);
                }
            }
        } finally {
            os.close(); in.close(); c.disconnect();
        }
    }

    private static String httpText(String url, AtomicBoolean cancel) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setInstanceFollowRedirects(true);
        c.setConnectTimeout(20000);
        c.setReadTimeout(30000);
        try {
            InputStream in = new BufferedInputStream(c.getInputStream());
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            byte[] b = new byte[8192];
            int n;
            while ((n = in.read(b)) > 0 && !cancel.get()) out.write(b, 0, n);
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        } finally { c.disconnect(); }
    }

    private static String sha256(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        InputStream in = new FileInputStream(f);
        try {
            byte[] b = new byte[65536];
            int n;
            while ((n = in.read(b)) > 0) md.update(b, 0, n);
        } finally { in.close(); }
        StringBuilder sb = new StringBuilder();
        for (byte x : md.digest()) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    /** Plain ZIP only (Release assets are repacked in CI from .tzst/.7z). */
    private static int unzip(File zip, File root, AtomicBoolean cancel) throws Exception {
        String rootPath = root.getCanonicalPath() + File.separator;
        int count = 0;
        ZipInputStream zis = new ZipInputStream(new BufferedInputStream(new FileInputStream(zip), 65536));
        try {
            ZipEntry e;
            byte[] buf = new byte[65536];
            while ((e = zis.getNextEntry()) != null) {
                if (cancel.get()) break;
                File target = new File(root, e.getName());
                if (!target.getCanonicalPath().startsWith(rootPath)) {
                    throw new IOException("zip-slip blocked: " + e.getName());
                }
                if (e.isDirectory()) {
                    if (!target.exists() && !target.mkdirs()) throw new IOException("mkdir " + target);
                    zis.closeEntry();
                    continue;
                }
                File parent = target.getParentFile();
                if (parent != null && !parent.exists() && !parent.mkdirs())
                    throw new IOException("mkdir " + parent);
                OutputStream os = new FileOutputStream(target);
                try {
                    int n;
                    while ((n = zis.read(buf)) > 0) os.write(buf, 0, n);
                } finally { os.close(); }
                if (isExecutable(e.getName())) target.setExecutable(true, false);
                count++;
                zis.closeEntry();
            }
        } finally { zis.close(); }
        return count;
    }

    private static boolean isExecutable(String name) {
        String lower = name.toLowerCase(Locale.US);
        return lower.endsWith(".sh") || lower.endsWith(".so") ||
               lower.contains("/bin/") || lower.endsWith("/box64") ||
               lower.endsWith("/wine64") || lower.endsWith("/wine") ||
               lower.endsWith("/xvfb") || lower.endsWith("/xserver") ||
               lower.endsWith("/proot") || lower.endsWith("/busybox");
    }
}
