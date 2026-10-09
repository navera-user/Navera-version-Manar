/* NAVERA Academy: loaded (LD_PRELOAD) only into the teacher's terminal that holds the full simulator.
 * Every TCP server started there (simulator page :8190/:8443, operator view :8181, ArduPilot SITL
 * :5760-5763) listens on the Jetson itself (127.0.0.1) instead of the whole network: other machines
 * on the Wi-Fi cannot open it, the academy (same machine) still proxies it for the teacher.
 * UDP is left alone (ROS 2 / DDS discovery uses it). NAVERA's own code is not changed. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <netinet/in.h>
#include <string.h>
#include <sys/socket.h>

typedef int (*bind_fn)(int, const struct sockaddr *, socklen_t);

int bind(int fd, const struct sockaddr *addr, socklen_t len)
{
    static bind_fn real_bind;
    if (!real_bind)
        real_bind = (bind_fn)dlsym(RTLD_NEXT, "bind");
    int type = 0;
    socklen_t tl = sizeof(type);
    if (addr && getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &tl) == 0 && type == SOCK_STREAM) {
        if (addr->sa_family == AF_INET && len >= (socklen_t)sizeof(struct sockaddr_in)) {
            struct sockaddr_in a;
            memcpy(&a, addr, sizeof(a));
            if (a.sin_addr.s_addr == htonl(INADDR_ANY)) {
                a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
                return real_bind(fd, (const struct sockaddr *)&a, sizeof(a));
            }
        } else if (addr->sa_family == AF_INET6 && len >= (socklen_t)sizeof(struct sockaddr_in6)) {
            struct sockaddr_in6 a;
            memcpy(&a, addr, sizeof(a));
            if (memcmp(&a.sin6_addr, &in6addr_any, sizeof(a.sin6_addr)) == 0) {
                a.sin6_addr = in6addr_loopback;
                return real_bind(fd, (const struct sockaddr *)&a, sizeof(a));
            }
        }
    }
    return real_bind(fd, addr, len);
}
