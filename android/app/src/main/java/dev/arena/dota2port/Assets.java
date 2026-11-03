package dev.arena.dota2port;

import android.content.Context;
import android.content.res.AssetManager;
import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.Charset;

/** Tiny asset helper: read text, recursively copy an asset directory to app-private files. */
final class Assets {
    private static final String TAG = "Dota2Assets";

    private Assets() {}

    static String readText(Context ctx, String assetPath) throws IOException {
        InputStream in = ctx.getAssets().open(assetPath);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return new String(out.toByteArray(), Charset.forName("UTF-8"));
        } finally {
            in.close();
        }
    }

    /** Copies assetDir/* into destDir, skipping files that are already up to date. */
    static void copy(Context ctx, String assetDir, File destDir, boolean executable) throws IOException {
        AssetManager am = ctx.getAssets();
        if (!destDir.exists() && !destDir.mkdirs()) {
            throw new IOException("cannot create " + destDir);
        }
        String[] children;
        try {
            children = am.list(assetDir);
        } catch (IOException e) {
            Log.w(TAG, "asset dir not found: " + assetDir);
            return;
        }
        if (children == null || children.length == 0) return;
        for (String child : children) {
            String sub = assetDir + "/" + child;
            String[] subChildren = am.list(sub);
            File target = new File(destDir, child);
            if (subChildren != null && subChildren.length > 0) {
                copy(ctx, sub, target, executable);
            } else {
                copyFile(am, sub, target);
                if (executable || child.endsWith(".sh")) {
                    //noinspection ResultOfMethodCallIgnored
                    target.setExecutable(true, false);
                }
            }
        }
    }

    private static void copyFile(AssetManager am, String asset, File target) throws IOException {
        InputStream in = am.open(asset);
        long size;
        try {
            size = in.available();
        } catch (IOException ignored) {
            size = -1;
        }
        if (target.exists() && size > 0 && target.length() == size) {
            in.close();
            return;
        }
        OutputStream out = new FileOutputStream(target);
        try {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            out.flush();
        } finally {
            out.close();
            in.close();
        }
    }
}
