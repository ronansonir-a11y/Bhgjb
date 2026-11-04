package dev.arena.dota2port;

import android.content.Context;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.Charset;

/** Unpacks assets, prepares the container environment and launches bootstrap.sh. */
final class RuntimeBootstrap {
    private static final String TAG = "Dota2Bootstrap";
    private static boolean nativeOk = false;
    private static Process process;

    static {
        try {
            System.loadLibrary("dota2bridge");
            nativeOk = true;
        } catch (Throwable t) {
            Log.i(TAG, "JNI probe not present (build with -PwithNdk to include it)");
        }
    }

    private static native String nativeProbe();

    private RuntimeBootstrap() {}

    static String probe() {
        if (!nativeOk) return "JNI: not built (optional)";
        try { return nativeProbe(); } catch (Throwable t) { return "JNI: " + t; }
    }

    private static File gameExe(LaunchConfig cfg) {
        return new File(cfg.gameRoot, cfg.exeRel);
    }

    /** Human-readable preflight. Never claims the game actually runs. */
    static String status(Context ctx, LaunchConfig cfg, int controls, int inputClients,
                         String bridgeRecent) {
        File files = ctx.getFilesDir();
        StringBuilder sb = new StringBuilder();
        sb.append("ABI: ").append(android.os.Build.SUPPORTED_ABIS[0]).append('\n');
        sb.append("JNI: ").append(probe()).append('\n');
        sb.append("targetSdk: 28 (exec from app-private files)\n");
        sb.append("gameRoot: ").append(cfg.gameRoot).append('\n');
        sb.append("preset: ").append(cfg.presetName).append('\n');
        sb.append("cmd: ").append(cfg.commandLine()).append('\n');
        sb.append('\n');
        sb.append(check(gameExe(cfg), "dota2.exe на /sdcard/Dota2/"));
        sb.append(check(new File(cfg.gameRoot, "game/dota/pak01_dir.vpk"), "game/dota/pak01_dir.vpk"));
        sb.append(check(new File(cfg.gameRoot, "game/core"), "game/core/ (Source 2 base resources)"));
        sb.append(check(new File(files, "runtime/rootfs.tzst"), "runtime/rootfs.tzst (Wine/glibc)"));
        sb.append(check(new File(files, "runtime/container_pattern.tzst"), "runtime/container_pattern.tzst (Wine prefix)"));
        sb.append(check(new File(files, "runtime/box64"), "runtime/box64"));
        sb.append(check(new File(files, "runtime/vortek"), "runtime/vortek (Vk-on-Vk)"));
        sb.append(check(new File(files, "runtime/goldberg/steam_api64.dll"), "runtime/goldberg/steam_api64.dll"));
        sb.append(check(new File(files, "dota2/bootstrap.sh"), "bootstrap.sh"));
        sb.append('\n');
        sb.append("overlay: ").append(controls).append(" controls, runtime clients: ")
          .append(inputClients).append('\n');
        if (bridgeRecent != null && bridgeRecent.trim().length() > 0) {
            sb.append("last input event: ").append(bridgeRecent.trim()).append('\n');
        }
        sb.append('\n');
        sb.append("NOTE: M0 (launcher) only. Bringing up Wine/Box64, the Win32→Android\n");
        sb.append("Vulkan WSI shim and an offline Steam/GC shim are M3–M6 milestones.\n");
        sb.append("See docs/03-PATH-B-CONTAINER.md. No Valve files are bundled in this APK.");
        return sb.toString();
    }

    private static String check(File f, String label) {
        return (f.exists() ? "[OK]   " : "[MISS] ") + label + '\n';
    }

    static synchronized boolean launch(Context ctx, LaunchConfig cfg) {
        try {
            File base = new File(ctx.getFilesDir(), "dota2");
            File runtimeOut = new File(ctx.getFilesDir(), "runtime");
            if (!base.exists() && !base.mkdirs()) return false;
            if (!runtimeOut.exists() && !runtimeOut.mkdirs()) return false;

            Assets.copy(ctx, "dota2", base, true);
            Assets.copy(ctx, "runtime", runtimeOut, true);
            patchSteamApi(cfg, runtimeOut);

            File log = new File(base, "launch.log");
            ProcessBuilder pb = new ProcessBuilder("sh", new File(base, "bootstrap.sh").getAbsolutePath());
            pb.directory(base);
            pb.redirectErrorStream(true);
            pb.redirectOutput(ProcessBuilder.Redirect.appendTo(log));
            pb.environment().put("RUNTIME_DIR", runtimeOut.getAbsolutePath());
            pb.environment().put("GAME_ROOT", cfg.gameRoot);
            pb.environment().put("DOTA_EXE", gameExe(cfg).getAbsolutePath());
            pb.environment().put("DOTA_ARGS", cfg.joinedArgs());
            pb.environment().put("DOTA_LOG", log.getAbsolutePath());
            pb.environment().put("WINEPREFIX", new File(runtimeOut, "prefix").getAbsolutePath());
            pb.environment().put("WINEARCH", "win64");
            pb.environment().put("WINEDEBUG", "-all");
            pb.environment().put("BOX64_DYNAREC", "1");
            pb.environment().put("BOX64_DYNAREC_BIGBLOCK", "1");
            pb.environment().put("BOX64_DYNAREC_SAFEFLAGS", "1");
            pb.environment().put("VK_ICD_FILENAMES", new File(runtimeOut, "vortek_icd.aarch64.json").getAbsolutePath());
            pb.environment().putAll(cfg.env);
            process = pb.start();
            Log.i(TAG, "bootstrap started, pid=" + process.toString());
            return true;
        } catch (Exception e) {
            Log.e(TAG, "launch failed", e);
            return false;
        }
    }

    /** Replaces steam_api64.dll with Goldberg only when the user opted in AND the
     *  emulator was bundled by CI. The original is always backed up first. */
    private static void patchSteamApi(LaunchConfig cfg, File runtimeOut) {
        if (!cfg.patchSteamApi) return;
        File emu = new File(runtimeOut, "goldberg/steam_api64.dll");
        if (!emu.exists()) return;
        File target = new File(cfg.gameRoot, "game/bin/win64/steam_api64.dll");
        if (!target.exists()) return;
        File backup = new File(cfg.gameRoot, "game/bin/win64/steam_api64.dll.valve");
        try {
            if (!backup.exists()) copy(target, backup);
            copy(emu, target);
            File interfaces = new File(runtimeOut, "goldberg/steam_interfaces.txt");
            if (interfaces.exists()) {
                copy(interfaces, new File(cfg.gameRoot, "game/bin/win64/steam_interfaces.txt"));
            }
        } catch (IOException e) {
            Log.w(TAG, "steam_api patch skipped: " + e.getMessage());
        }
    }

    private static void copy(File from, File to) throws IOException {
        java.io.InputStream in = new FileInputStream(from);
        java.io.OutputStream out = new java.io.FileOutputStream(to);
        try {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        } finally {
            out.close();
            in.close();
        }
    }

    static String readLog(Context ctx) {
        File log = new File(new File(ctx.getFilesDir(), "dota2"), "launch.log");
        if (!log.exists()) return "Лог пока пуст — запустите контейнер.";
        try {
            byte[] data = new byte[(int) Math.min(log.length(), 65536)];
            FileInputStream in = new FileInputStream(log);
            int n = in.read(data);
            in.close();
            return new String(data, 0, Math.max(0, n), Charset.forName("UTF-8"));
        } catch (IOException e) {
            return "Не удалось прочитать лог: " + e.getMessage();
        }
    }

    static boolean isRunning() {
        return process != null && process.isAlive();
    }
}
