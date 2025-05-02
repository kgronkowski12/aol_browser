cmake_minimum_required(VERSION 3.10)
project(SimpleBrowser)

# Set C++ standard
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find required packages
find_package(PkgConfig REQUIRED)
pkg_check_modules(GTK3 REQUIRED gtk+-3.0)
pkg_check_modules(WEBKIT REQUIRED webkit2gtk-4.0)

# Include directories
include_directories(${GTK3_INCLUDE_DIRS} ${WEBKIT_INCLUDE_DIRS})

# Link directories
link_directories(${GTK3_LIBRARY_DIRS} ${WEBKIT_LIBRARY_DIRS})

# Add compile options
add_compile_options(${GTK3_CFLAGS_OTHER} ${WEBKIT_CFLAGS_OTHER})

# Add executable
add_executable(SimpleBrowser SimpleBrowser.cpp)

# Link libraries
target_link_libraries(SimpleBrowser ${GTK3_LIBRARIES} ${WEBKIT_LIBRARIES})