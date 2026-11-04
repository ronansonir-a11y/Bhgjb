cmake_minimum_required(VERSION 3.22.1)
project("dota2bridge" C)

# Tiny arm64-v8a JNI probe. The real container input sink (Wine/XTest bridge)
# is milestone M4 and is intentionally NOT faked here.
add_library(dota2bridge SHARED dota2_bridge.c)

find_library(log-lib log)
target_link_libraries(dota2bridge ${log-lib})
