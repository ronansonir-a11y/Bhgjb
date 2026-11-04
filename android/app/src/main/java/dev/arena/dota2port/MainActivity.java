package dev.arena.dota2port;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputType;
import android.util.Log;
import android.widget.FrameLayout;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.concurrent.atomic.AtomicBoolean;

/** Phone-first launcher: demo, runtime downloader, content downloader, container. */
public class MainActivity extends Activity {
    private static final String TAG = "Dota2Main";
    private static final int REQ_STORAGE = 570;

    private TextView status, progressText;
    private ProgressBar progress;
    private LinearLayout panel;
    private FrameLayout root, demoHost;
    private TouchOverlayView overlay;
    private DemoSurfaceView demo;
    private LaunchConfig cfg;
    private final AtomicBoolean cancelJob = new AtomicBoolean(false);
    private boolean demoActive;

    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        root = findViewById(R.id.root);
        panel = findViewById(R.id.panel);
        demoHost = findViewById(R.id.demoHost);
        status = findViewById(R.id.status);
        progress = findViewById(R.id.progress);
        progressText = findViewById(R.id.progressText);
        Button btnDemo = findViewById(R.id.btnDemo);
        Button btnInstall = findViewById(R.id.btnInstall);
        Button btnLaunch = findViewById(R.id.btnLaunch);
        Button btnContent = findViewById(R.id.btnContent);
        Button btnCheck = findViewById(R.id.btnCheck);
        Button btnLog = findViewById(R.id.btnLog);
        Button btnAccess = findViewById(R.id.btnAccess);

        try {
            cfg = LaunchConfig.load(this);
        } catch (Exception e) {
            status.setText("Ошибка launch.json: " + e.getMessage());
            return;
        }

        InputBridge.get().start(cfg.socketName);
        try {
            overlay = new TouchOverlayView(this, Assets.readText(this, "dota2/controls.json"));
            overlay.setControlsEnabled(false);
        } catch (Exception e) {
            Log.e(TAG, "overlay unavailable", e);
        }

        btnDemo.setOnClickListener(v -> startDemo());
        btnInstall.setOnClickListener(v -> {
            cancelJob.set(false);
            setBusy(true, "Подготовка…");
            RuntimeInstaller.install(this, new RuntimeInstaller.Progress() {
                @Override public void onStage(String label, int pct, String detail) {
                    ui.post(() -> { progressText.setText(label + " · " + detail);
                                    progress.setProgress(pct); });
                }
                @Override public void onDone(boolean ok, String msg) {
                    ui.post(() -> { setBusy(false, msg); refresh();
                                    toast(ok ? "Рантайм установлен" : msg); });
                }
            }, cancelJob);
        });
        btnLaunch.setOnClickListener(v -> launchContainer());
        btnContent.setOnClickListener(v -> askContentUrl());
        btnCheck.setOnClickListener(v -> refresh());
        btnLog.setOnClickListener(v -> status.setText(
                "──── container.log ────\n" + ContainerSession.liveLog() +
                "\n──── launch.log ────\n" + RuntimeBootstrap.readLog(this) +
                "\n──── input events ────\n" + InputBridge.get().recentEvents()));
        btnAccess.setOnClickListener(v -> requestAllFilesAccess());

        refresh();
        requestStorageIfNeeded();
        if (cfg.demoOnStart) ui.postDelayed(this::startDemo, 700);
        else if (cfg.autoLaunch) ui.postDelayed(this::launchContainer, 1200);
    }

    private void setBusy(boolean busy, String text) {
        progress.setVisibility(busy ? android.view.View.VISIBLE : android.view.View.GONE);
        progressText.setVisibility(busy ? android.view.View.VISIBLE : android.view.View.GONE);
        if (busy) { progress.setProgress(0); progressText.setText(text); }
    }

    private void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }

    // ---------------------------------------------------------------- demo ---
    private void startDemo() {
        if (demoActive) return;
        demoActive = true;
        panel.setVisibility(android.view.View.GONE);
        demoHost.setVisibility(android.view.View.VISIBLE);
        demo = new DemoSurfaceView(this);
        demoHost.addView(demo, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        if (overlay != null) {
            if (overlay.getParent() != null) ((FrameLayout) overlay.getParent()).removeView(overlay);
            root.addView(overlay, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
            overlay.setControlsEnabled(true);
        }
        toast("ДЕМО: наш рендерер, не Source 2. Нажмите «Назад» для меню.");
    }

    private void stopDemo() {
        if (!demoActive) return;
        demoActive = false;
        if (demo != null) { demo.stop(); demoHost.removeView(demo); demo = null; }
        demoHost.setVisibility(android.view.View.GONE);
        panel.setVisibility(android.view.View.VISIBLE);
        if (overlay != null) overlay.setControlsEnabled(false);
        refresh();
    }

    @Override public void onBackPressed() {
        if (demoActive) { stopDemo(); return; }
        super.onBackPressed();
    }

    // ------------------------------------------------------------- container --
    private void launchContainer() {
        stopDemo();
        if (ContainerSession.isRunning()) { toast("Контейнер уже запущен"); return; }
        setBusy(true, "Запуск контейнера…");
        ContainerSession.start(this, cfg, new ContainerSession.Callback() {
            @Override public void onLine(String line) {
                ui.post(() -> {
                    progressText.setText(line.length() > 90 ? line.substring(0, 90) : line);
                    status.append(line + "\n");
                });
            }
            @Override public void onFinished(int code) {
                ui.post(() -> { setBusy(false, "Код завершения: " + code); refresh(); });
            }
        });
        if (overlay != null) overlay.setControlsEnabled(true);
    }

    // --------------------------------------------------------------- content --
    private void askContentUrl() {
        if (!ContentInstaller.hasAllFilesAccess()) {
            new AlertDialog.Builder(this)
                .setTitle("Нужен доступ к /sdcard/Dota2/")
                .setMessage("На Android 11+ включите «Доступ ко всем файлам» для этого приложения, затем повторите.")
                .setPositiveButton("Открыть настройки", (d, w) -> requestAllFilesAccess())
                .setNegativeButton("Отмена", null).show();
            return;
        }
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setHint("https://…/dota2-beta.zip (ваша личная ссылка)");
        new AlertDialog.Builder(this)
            .setTitle("Загрузить файлы игры")
            .setMessage("Вставьте приватную ссылку на ZIP с ВАШЕЙ собственной копией папки «dota 2 beta». Valve-файлы не хранятся в репозитории и не скачиваются приложением автоматически.")
            .setView(input)
            .setPositiveButton("Скачать", (d, w) -> {
                String url = input.getText().toString().trim();
                if (!url.startsWith("http")) { toast("Нужен http(s) URL"); return; }
                cancelJob.set(false);
                setBusy(true, "Загрузка контента…");
                ContentInstaller.install(url, new ContentInstaller.Progress() {
                    @Override public void onStage(String label, int pct, String detail) {
                        ui.post(() -> { progressText.setText(label + " · " + detail);
                                        progress.setProgress(pct); });
                    }
                    @Override public void onDone(boolean ok, String msg) {
                        ui.post(() -> { setBusy(false, msg); refresh(); toast(msg); });
                    }
                }, cancelJob);
            })
            .setNegativeButton("Отмена", null).show();
    }

    private void requestAllFilesAccess() {
        if (Build.VERSION.SDK_INT >= 30 && !ContentInstaller.hasAllFilesAccess()) {
            try {
                Intent i = new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION);
                i.setData(Uri.parse("package:" + getPackageName()));
                startActivity(i);
            } catch (Exception e) {
                startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION));
            }
        } else {
            toast("Доступ к файлам уже есть");
        }
    }

    // ------------------------------------------------------------ permissions -
    private void requestStorageIfNeeded() {
        if (Build.VERSION.SDK_INT >= 23) {
            requestPermissions(new String[]{
                    Manifest.permission.READ_EXTERNAL_STORAGE,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_STORAGE);
        }
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQ_STORAGE) refresh();
    }

    private void refresh() {
        if (cfg == null) return;
        StringBuilder sb = new StringBuilder(RuntimeBootstrap.status(this, cfg,
                overlay == null ? 0 : overlay.getControlCount(),
                InputBridge.get().clientCount(), null));
        sb.append("\n\nРантайм: ").append(RuntimeInstaller.installedMarker(this).exists()
                ? "установлен" : "НЕ установлен (кнопка «Скачать рантайм»)");
        sb.append("\nКонтент: ").append(new java.io.File(cfg.gameRoot, "game/bin/win64/dota2.exe").exists()
                ? "dota2.exe найден" : "нет dota2.exe (демо работает без него)");
        sb.append("\nДоступ ко всем файлам: ").append(ContentInstaller.hasAllFilesAccess() ? "есть" : "нет");
        sb.append("\nКонтейнер: ").append(ContainerSession.isRunning() ? "запущен" : "остановлен");
        sb.append("\n\nДЕМО-режим работает сразу после установки, без 30 ГБ VPK.");
        status.setText(sb.toString());
    }

    @Override protected void onDestroy() {
        stopDemo();
        ContainerSession.stop();
        super.onDestroy();
    }
}
