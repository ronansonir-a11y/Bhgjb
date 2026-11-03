package dev.arena.dota2port;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Parses assets/dota2/launch.json. No game code, only launch parameters. */
final class LaunchConfig {
    final String gameRoot;
    final String exeRel;
    final String presetName;
    final String socketName;
    final boolean autoLaunch;
    final boolean patchSteamApi;
    final List<String> args = new ArrayList<>();
    final Map<String, String> env = new LinkedHashMap<>();

    private LaunchConfig(JSONObject root) throws Exception {
        gameRoot = root.optString("gameRoot", "/sdcard/Dota2");
        exeRel = root.optString("exe", "game/bin/win64/dota2.exe");
        presetName = root.optString("preset", "requested");
        socketName = root.optString("socket", "dota2-input");
        autoLaunch = root.optBoolean("autoLaunch", false);
        patchSteamApi = root.optBoolean("patchSteamApi", true);

        JSONObject presets = root.getJSONObject("presets");
        JSONObject preset = presets.optJSONObject(presetName);
        if (preset == null) throw new IllegalArgumentException("unknown preset: " + presetName);
        JSONArray arr = preset.getJSONArray("args");
        for (int i = 0; i < arr.length(); i++) args.add(arr.getString(i));

        JSONObject e = root.optJSONObject("env");
        if (e != null) {
            java.util.Iterator<String> it = e.keys();
            while (it.hasNext()) {
                String k = it.next();
                env.put(k, e.optString(k));
            }
        }
    }

    static LaunchConfig load(Context ctx) throws Exception {
        return new LaunchConfig(new JSONObject(Assets.readText(ctx, "dota2/launch.json")));
    }

    String joinedArgs() {
        StringBuilder sb = new StringBuilder();
        for (String a : args) {
            if (sb.length() > 0) sb.append(' ');
            sb.append(a);
        }
        return sb.toString();
    }

    String commandLine() {
        return "dota2.exe " + joinedArgs();
    }
}
