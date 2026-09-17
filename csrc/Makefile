CXX ?= clang++
CXXFLAGS = -std=c++20 -O3 -Wall -Wextra -Werror -fPIC -arch arm64
TARGET = libsentinel_core.dylib

all: $(TARGET)

$(TARGET): sentinel_core.cpp sentinel_core.hpp
	$(CXX) $(CXXFLAGS) -shared -o $@ sentinel_core.cpp

clean:
	rm -f $(TARGET) *.o

.PHONY: all clean
