package dev.arena.dota2port;

import android.Manifest;
import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.FrameLayout;
import android.widget.Button;
import android.widget.TextView;

/** Launcher shell: preflight status, launch, log, and the Dota 2 touch overlay. */
public class MainActivity extends Activity {
    private static final String TAG = "Dota2Main";
    private static final int REQ_STORAGE = 570;

    private TextView status;
    private TouchOverlayView overlay;
    private LaunchConfig cfg;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        status = findViewById(R.id.status);
        Button btnLaunch = findViewById(R.id.btnLaunch);
        Button btnCheck = findViewById(R.id.btnCheck);
        Button btnLog = findViewById(R.id.btnLog);

        try {
            cfg = LaunchConfig.load(this);
        } catch (Exception e) {
            Log.e(TAG, "launch.json missing or invalid", e);
            status.setText("Ошибка конфигурации: " + e.getMessage());
            return;
        }

        InputBridge.get().start(cfg.socketName);
        try {
            overlay = new TouchOverlayView(this, Assets.readText(this, "dota2/controls.json"));
            overlay.setControlsEnabled(false); // pass touches to the buttons until launch
            FrameLayout root = findViewById(R.id.root);
            root.addView(overlay, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT));
        } catch (Exception e) {
            Log.e(TAG, "overlay unavailable", e);
        }

        refresh();
        requestStorageIfNeeded();

        btnLaunch.setOnClickListener(v -> new Thread(() -> {
            boolean ok = RuntimeBootstrap.launch(MainActivity.this, cfg);
            runOnUiThread(() -> {
                if (overlay != null) overlay.setControlsEnabled(ok);
                refresh();
                status.append(ok ? "\n[bootstrap] процесс запущен, см. Лог."
                                 : "\n[bootstrap] не удалось стартовать, см. Лог.");
            });
        }, "dota2-launch").start());

        btnCheck.setOnClickListener(v -> refresh());
        btnLog.setOnClickListener(v -> status.setText(
                "──── launch.log ────\n" + RuntimeBootstrap.readLog(this)
                        + "\n──── input events ────\n" + InputBridge.get().recentEvents()));

        if (cfg.autoLaunch) {
            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                if (!RuntimeBootstrap.isRunning()) btnLaunch.performClick();
            }, 1200);
        }
    }

    private void requestStorageIfNeeded() {
        if (Build.VERSION.SDK_INT >= 23) {
            requestPermissions(new String[]{
                    Manifest.permission.READ_EXTERNAL_STORAGE,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_STORAGE);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQ_STORAGE) refresh();
    }

    private void refresh() {
        if (cfg == null) return;
        int controls = overlay == null ? 0 : overlay.getControlCount();
        status.setText(RuntimeBootstrap.status(this, cfg, controls,
                InputBridge.get().clientCount(), null));
    }
}
