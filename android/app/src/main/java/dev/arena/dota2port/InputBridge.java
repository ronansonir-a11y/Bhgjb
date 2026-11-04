package dev.arena.dota2port;

import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.util.Log;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.Charset;
import java.util.LinkedList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Touch overlay -> runtime event transport.
 *
 * Protocol: newline-delimited JSON over an Android abstract UNIX socket:
 *   {"t":"down","id":"q","binding":"KEY_Q","type":"button"}
 *   {"t":"move","id":"trackpad","dx":3.5,"dy":-1.0,"binding":"MOUSE_MOVE_UP"}
 *   {"t":"up","id":"q","binding":"KEY_Q"}
 *
 * The runtime side (Wine XServer / XTest / SendInput bridge, milestone M4) connects
 * as a client. Until it does, events are still recorded in a ring buffer so the
 * overlay remains testable. This class does NOT claim to inject into Windows.
 */
final class InputBridge {
    private static final String TAG = "Dota2Input";
    private static final Charset UTF8 = Charset.forName("UTF-8");
    private static final int MAX_RECENT = 200;
    private static final InputBridge INSTANCE = new InputBridge();

    private final List<OutputStream> clients = new CopyOnWriteArrayList<>();
    private final LinkedList<String> recent = new LinkedList<>();
    private volatile LocalServerSocket server;

    static InputBridge get() { return INSTANCE; }

    synchronized void start(String socketName) {
        if (server != null) return;
        Thread t = new Thread(() -> serve(socketName), "dota2-input-server");
        t.setDaemon(true);
        t.start();
    }

    private void serve(String socketName) {
        try {
            LocalServerSocket s = new LocalServerSocket(socketName);
            server = s;
            Log.i(TAG, "listening on abstract socket '" + socketName + "'");
            while (true) {
                final LocalSocket client = s.accept();
                Log.i(TAG, "runtime client connected");
                OutputStream os = client.getOutputStream();
                clients.add(os);
                Thread watcher = new Thread(() -> {
                    try {
                        BufferedReader r = new BufferedReader(new InputStreamReader(client.getInputStream()));
                        while (r.readLine() != null) { /* drain until disconnect */ }
                    } catch (IOException ignored) {
                    } finally {
                        clients.remove(os);
                        try { client.close(); } catch (IOException ignored) {}
                    }
                }, "dota2-input-client");
                watcher.setDaemon(true);
                watcher.start();
            }
        } catch (IOException e) {
            Log.w(TAG, "input server stopped: " + e.getMessage());
            server = null;
        }
    }

    void send(String eventJson) {
        synchronized (recent) {
            recent.addLast(eventJson);
            if (recent.size() > MAX_RECENT) recent.removeFirst();
        }
        byte[] payload = (eventJson + "\n").getBytes(UTF8);
        for (OutputStream os : clients) {
            try {
                os.write(payload);
                os.flush();
            } catch (IOException e) {
                clients.remove(os);
            }
        }
    }

    String recentEvents() {
        synchronized (recent) {
            StringBuilder sb = new StringBuilder();
            for (String s : recent) sb.append(s).append('\n');
            return sb.toString();
        }
    }

    int clientCount() { return clients.size(); }
}
