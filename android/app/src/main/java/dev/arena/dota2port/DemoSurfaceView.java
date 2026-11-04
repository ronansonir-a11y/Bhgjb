package dev.arena.dota2port;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.SurfaceHolder;
import android.view.SurfaceView;

import org.json.JSONObject;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * DEMO renderer -- our own tiny SurfaceView "engine", NOT Source 2 and NOT Dota 2.
 *
 * It exists so a freshly installed APK is immediately verifiable on a phone,
 * with all 28 touch controls producing visible feedback. It requires zero
 * downloads and zero Valve files.
 */
public class DemoSurfaceView extends SurfaceView implements SurfaceHolder.Callback,
        InputBridge.Listener, Runnable {

    private static final String TAG = "Dota2Demo";
    private final Paint bg = new Paint();
    private final Paint grid = new Paint();
    private final Paint hero = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint targetPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint spell = new Paint(Paint.ANTI_ALIAS_FLAG);

    private volatile boolean running;
    private Thread thread;
    private int w, h;
    private float camX, camY, zoom = 1f;
    private float heroX = 0.5f, heroY = 0.55f;
    private float targetX = 0.5f, targetY = 0.55f;
    private int events;
    private String lastBinding = "—";
    private long pulseUntil;
    private int pulseColor = Color.WHITE;
    private final Map<String, Integer> counters = new LinkedHashMap<>();
    private final StringBuilder log = new StringBuilder();
    private final Handler ui = new Handler(Looper.getMainLooper());

    public DemoSurfaceView(Context ctx) {
        super(ctx);
        getHolder().addCallback(this);
        getHolder().setFormat(PixelFormat.OPAQUE);
        setZOrderOnTop(false);
        initPaints();
    }

    private void initPaints() {
        bg.setColor(0xFF0E1116);
        grid.setColor(0x332A3442);
        grid.setStrokeWidth(1f);
        hero.setColor(0xFFC23B22);
        hero.setStyle(Paint.Style.FILL);
        targetPaint.setColor(0xFFF0C674);
        targetPaint.setStyle(Paint.Style.STROKE);
        targetPaint.setStrokeWidth(3f);
        text.setColor(0xFFE8EAED);
        text.setTextSize(22f);
        text.setFakeBoldText(true);
        spell.setStyle(Paint.Style.STROKE);
        spell.setStrokeWidth(8f);
    }

    public void start() {
        InputBridge.get().addListener(this);
        running = true;
        thread = new Thread(this, "dota2-demo-render");
        thread.start();
    }

    public void stop() {
        running = false;
        InputBridge.get().removeListener(this);
        if (thread != null) {
            try { thread.join(400); } catch (InterruptedException ignored) {}
            thread = null;
        }
    }

    @Override public void surfaceCreated(SurfaceHolder holder) { if (!running) start(); }
    @Override public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
        w = width;
        h = height;
    }
    @Override public void surfaceDestroyed(SurfaceHolder holder) { stop(); }

    @Override public void onEvent(String json) {
        events++;
        try {
            JSONObject o = new JSONObject(json);
            String t = o.optString("t", "");
            String binding = o.optString("binding", "NONE");
            String id = o.optString("id", "?");
            if ("up".equals(t)) return;
            lastBinding = binding + " (" + id + ")";
            Integer old = counters.get(binding);
            counters.put(binding, old == null ? 1 : old + 1);
            if (counters.size() > 8) counters.remove(counters.keySet().iterator().next());
            apply(binding, o);
            log.insert(0, lastBinding + "\n");
            if (log.length() > 600) log.setLength(600);
        } catch (Exception e) {
            Log.w(TAG, "bad event", e);
        }
    }

    private void apply(String b, JSONObject o) {
        if (b.contains("MOUSE_RIGHT") || b.contains("MOVE") || b.contains("RIGHT")) {
            // Right-click movement: advance the hero toward a new destination.
            targetX = clamp(targetX + 0.06f * (float) Math.cos(events * 0.7));
            targetY = clamp(targetY + 0.06f * (float) Math.sin(events * 0.9));
            pulse(0xFFC23B22);
        } else if (b.contains("CAM") || b.contains("ARROW") || b.contains("GRIP")) {
            camX += o.optDouble("dx", 2) * 0.4f;
            camY += o.optDouble("dy", 2) * 0.4f;
            pulse(0xFF2F6FD0);
        } else if (b.contains("SCROLL") || b.contains("ZOOM")) {
            zoom = clamp(zoom + 0.05f, 0.6f, 1.8f);
            pulse(0xFF2F6FD0);
        } else if (b.contains("KEY_Q") || b.contains("KEY_W") || b.contains("KEY_E") ||
                   b.contains("KEY_D") || b.contains("KEY_F") || b.contains("KEY_R")) {
            pulse(0xFFE0A040);
        } else if (b.contains("ITEM") || b.matches(".*KEY_[1-6].*")) {
            pulse(0xFF66BB6A);
        } else {
            pulse(0xFFE8EAED);
        }
    }

    private void pulse(int color) {
        pulseColor = color;
        pulseUntil = System.currentTimeMillis() + 260;
    }

    private static float clamp(float v) { return clamp(v, 0.08f, 0.92f); }
    private static float clamp(float v, float lo, float hi) {
        return v < lo ? lo : (v > hi ? hi : v);
    }

    @Override public void run() {
        while (running) {
            Canvas c = null;
            try {
                c = getHolder().lockCanvas();
                if (c != null) synchronized (getHolder()) { draw(c); }
            } catch (Throwable t) {
                Log.w(TAG, "render", t);
            } finally {
                if (c != null) try { getHolder().unlockCanvasAndPost(c); } catch (Throwable ignored) {}
            }
            try { Thread.sleep(16); } catch (InterruptedException e) { return; }
        }
    }

    private void draw(Canvas c) {
        if (w <= 0 || h <= 0) { w = getWidth(); h = getHeight(); }
        c.drawColor(0xFF0E1116);
        bg.setColor(0xFF0E1116);
        c.drawRect(0, 0, w, h, bg);
        // camera grid
        float step = 64 * zoom;
        float ox = (camX % step + step) % step;
        float oy = (camY % step + step) % step;
        for (float x = ox; x < w; x += step) c.drawLine(x, 0, x, h, grid);
        for (float y = oy; y < h; y += step) c.drawLine(0, y, w, y, grid);

        // hero eases toward its ordered destination
        heroX += (targetX - heroX) * 0.06f;
        heroY += (targetY - heroY) * 0.06f;
        float hx = heroX * w, hy = heroY * h;
        c.drawCircle(targetX * w, targetY * h, 18, targetPaint);
        if (System.currentTimeMillis() < pulseUntil) {
            spell.setColor(pulseColor);
            float r = 30 + (pulseUntil - System.currentTimeMillis()) * 0.25f;
            c.drawCircle(hx, hy, r, spell);
        }
        c.drawCircle(hx, hy, 22, hero);

        // HUD
        float y = 34;
        c.drawText("ДЕМО-РЕЖИМ · наш рендерер, НЕ Source 2 / НЕ Dota 2", 16, y, text);
        y += 30;
        c.drawText("Событий: " + events + "   Камера: " + (int) camX + "," + (int) camY +
                   "   Zoom: " + String.format(java.util.Locale.US, "%.2f", zoom), 16, y, text);
        y += 30;
        c.drawText("Последняя кнопка: " + lastBinding, 16, y, text);
        y += 30;
        c.drawText("Нажмите «Назад», чтобы вернуться в меню", 16, y, text);
        y += 34;
        for (Map.Entry<String, Integer> e : counters.entrySet()) {
            c.drawText("  " + e.getKey() + " × " + e.getValue(), 16, y, text);
            y += 26;
        }
    }
}
