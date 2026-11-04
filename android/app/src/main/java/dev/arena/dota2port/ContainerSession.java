package dev.arena.dota2port;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * Real container launch path (M3). Executes bootstrap.sh, which autodiscovers
 * Box64/Wine/rootfs inside the runtime installed by RuntimeInstaller and execs
 * dota2.exe through them. stdout/stderr is streamed to the UI and to launch.log.
 *
 * Honest boundary: Winlator's Java XServer, the Win32->Android Vulkan WSI thunk
 * and the offline Game Coordinator shim are NOT implemented here (M4-M6).
 */
public final class ContainerSession {
    private static final String TAG = "Dota2Session";
    private static volatile Process process;
    private static final StringBuilder liveLog = new StringBuilder();
    private static final Handler UI = new Handler(Looper.getMainLooper());

    public interface Callback {
        void onLine(String line);
        void onFinished(int code);
    }

    private ContainerSession() {}

    public static boolean isRunning() { return process != null && process.isAlive(); }

    public static String liveLog() {
        synchronized (liveLog) { return liveLog.toString(); }
    }

    public static void start(Context ctx, LaunchConfig cfg, Callback cb) {
        if (isRunning()) { cb.onLine("[session] уже запущен"); cb.onFinished(-1); return; }
        synchronized (liveLog) { liveLog.setLength(0); }

        new Thread(() -> {
            File base = new File(ctx.getFilesDir(), "dota2");
            File runtime = RuntimeInstaller.runtimeDir(ctx);
            File log = new File(base, "launch.log");
            try {
                if (!base.exists() && !base.mkdirs()) throw new Exception("cannot create " + base);
                Assets.copy(ctx, "dota2", base, true);
                if (!RuntimeInstaller.installedMarker(ctx).exists()) {
                    emit(cb, "[session] РАНТАЙМ НЕ УСТАНОВЛЕН. Нажмите «Скачать рантайм».");
                }
                File shell = new File(base, "bootstrap.sh");
                shell.setExecutable(true, false);

                ProcessBuilder pb = new ProcessBuilder("sh", shell.getAbsolutePath());
                pb.directory(base);
                pb.redirectErrorStream(true);
                pb.environment().put("RUNTIME_DIR", runtime.getAbsolutePath());
                pb.environment().put("GAME_ROOT", cfg.gameRoot);
                pb.environment().put("DOTA_EXE", new File(cfg.gameRoot, cfg.exeRel).getAbsolutePath());
                pb.environment().put("DOTA_ARGS", cfg.joinedArgs());
                pb.environment().put("DOTA_LOG", log.getAbsolutePath());
                pb.environment().put("WINEPREFIX", new File(runtime, "prefix").getAbsolutePath());
                pb.environment().put("WINEARCH", "win64");
                pb.environment().put("WINEDEBUG", "-all");
                pb.environment().put("DISPLAY", ":0");
                pb.environment().put("XDG_RUNTIME_DIR", ctx.getFilesDir().getAbsolutePath());
                for (Map.Entry<String, String> e : cfg.env.entrySet())
                    pb.environment().put(e.getKey(), e.getValue());

                emit(cb, "[session] exec: " + cfg.commandLine());
                process = pb.start();
                FileOutputStream fos = new FileOutputStream(log, false);
                BufferedReader r = new BufferedReader(
                        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
                String line;
                while ((line = r.readLine()) != null) {
                    emit(cb, line);
                    fos.write((line + "\n").getBytes(StandardCharsets.UTF_8));
                    fos.flush();
                }
                fos.close();
                int code = process.waitFor();
                emit(cb, "[session] процесс завершился, код " + code);
                cb.onFinished(code);
            } catch (Exception e) {
                Log.e(TAG, "start failed", e);
                emit(cb, "[session] ОШИБКА: " + e.getMessage());
                cb.onFinished(-2);
            } finally {
                process = null;
            }
        }, "dota2-container").start();
    }

    private static void emit(Callback cb, String line) {
        synchronized (liveLog) {
            liveLog.append(line).append('\n');
            if (liveLog.length() > 65536) liveLog.delete(0, liveLog.length() - 65536);
        }
        UI.post(() -> cb.onLine(line));
    }

    public static void stop() {
        Process p = process;
        if (p != null) p.destroy();
    }
}
