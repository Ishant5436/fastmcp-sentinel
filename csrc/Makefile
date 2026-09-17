CXX ?= clang++
UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Darwin)
    TARGET = libsentinel_core.dylib
    CXXFLAGS = -std=c++20 -O3 -Wall -Wextra -Werror -fPIC -arch arm64
else
    TARGET = libsentinel_core.so
    CXXFLAGS = -std=c++20 -O3 -Wall -Wextra -Werror -fPIC
endif

all: $(TARGET)

$(TARGET): sentinel_core.cpp sentinel_core.hpp
	$(CXX) $(CXXFLAGS) -shared -o $@ sentinel_core.cpp

clean:
	rm -f libsentinel_core.dylib libsentinel_core.so *.o

.PHONY: all clean
