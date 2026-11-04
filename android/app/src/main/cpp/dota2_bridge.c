/*
 * dota2_bridge.c — minimal arm64-v8a JNI probe for the Dota 2 container shell.
 *
 * This library exists to prove the APK really carries an arm64-v8a native
 * component built with the Android NDK. It does NOT emulate x86-64, load PE
 * images or inject input. The input event transport is InputBridge.java
 * (newline-delimited JSON over an abstract UNIX socket); the runtime-side
 * Wine/XTest consumer is milestone M4, see docs/03-PATH-B-CONTAINER.md.
 */
#include <jni.h>
#include <android/log.h>

#define TAG "dota2bridge"

JNIEXPORT jstring JNICALL
Java_dev_arena_dota2port_RuntimeBootstrap_nativeProbe(JNIEnv *env, jclass clazz) {
    (void)clazz;
#if defined(__aarch64__)
    __android_log_write(ANDROID_LOG_INFO, TAG, "arm64-v8a native bridge loaded");
    return (*env)->NewStringUTF(env, "arm64-v8a native bridge OK");
#else
    __android_log_write(ANDROID_LOG_WARN, TAG, "unexpected ABI");
    return (*env)->NewStringUTF(env, "non-ARM64 ABI (unsupported)");
#endif
}
