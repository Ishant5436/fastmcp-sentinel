CXX ?= c++
UNAME_S := $(shell uname -s)

# Assertions are intentionally kept enabled (no -DNDEBUG): they are part of the
# Power of 10 safety contract. Override ARCHFLAGS for cross/universal builds,
# e.g. `make ARCHFLAGS="-arch arm64 -arch x86_64"` on macOS.
ARCHFLAGS ?=
CXXFLAGS ?= -O2
CXXFLAGS += -std=c++20 -Wall -Wextra -Wpedantic -Wshadow -Werror -fPIC $(ARCHFLAGS)

ifeq ($(UNAME_S),Darwin)
    TARGET = libsentinel_core.dylib
    LDFLAGS += -dynamiclib
else
    TARGET = libsentinel_core.so
    LDFLAGS += -shared
endif

all: $(TARGET)

$(TARGET): sentinel_core.cpp sentinel_core.hpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ sentinel_core.cpp

clean:
	rm -f libsentinel_core.dylib libsentinel_core.so *.o

.PHONY: all clean
