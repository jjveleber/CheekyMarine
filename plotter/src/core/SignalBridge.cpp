#include "core/SignalBridge.h"
#include <QDebug>
#include <QSocketNotifier>
#include <cerrno>
#include <csignal>
#include <sys/socket.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace {
volatile sig_atomic_t g_writeFd = -1; // write end of the active bridge (non-blocking)
SignalBridge* g_instance = nullptr;

void handler(int signo) {
    const int savedErrno = errno;
    const char b = static_cast<char>(signo);
    if (g_writeFd >= 0) {
        [[maybe_unused]] ssize_t n = ::write(g_writeFd, &b, 1);
    }
    errno = savedErrno;
}
} // namespace

struct SignalBridge::Saved {
    std::vector<std::pair<int, struct sigaction>> actions;
};

SignalBridge::SignalBridge(std::initializer_list<int> signos, QObject* parent) : QObject(parent) {
    if (g_instance) {
        qWarning() << "SignalBridge: a second bridge is ignored";
        return;
    }
    if (::socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, fds_) != 0) {
        qWarning() << "SignalBridge: socketpair failed, signals will not quit cleanly";
        fds_[0] = fds_[1] = -1;
        return;
    }
    g_instance = this;
    g_writeFd = fds_[1];
    notifier_ = new QSocketNotifier(fds_[0], QSocketNotifier::Read, this);
    connect(notifier_, &QSocketNotifier::activated, this, &SignalBridge::onReadable);

    saved_ = new Saved;
    for (int sig : signos) {
        // A signal the process was told to ignore (SIGHUP under nohup) stays ignored.
        struct sigaction current {};
        if (::sigaction(sig, nullptr, &current) == 0 && current.sa_handler == SIG_IGN) continue;
        struct sigaction sa {};
        sa.sa_handler = handler;
        sigemptyset(&sa.sa_mask);
        sa.sa_flags = SA_RESTART;
        struct sigaction old {};
        if (::sigaction(sig, &sa, &old) == 0) saved_->actions.emplace_back(sig, old);
    }
}

SignalBridge::~SignalBridge() {
    if (saved_) {
        for (auto& [sig, old] : saved_->actions) ::sigaction(sig, &old, nullptr);
        delete saved_;
    }
    if (g_instance == this) {
        g_writeFd = -1;
        g_instance = nullptr;
    }
    if (fds_[0] >= 0) ::close(fds_[0]);
    if (fds_[1] >= 0) ::close(fds_[1]);
}

void SignalBridge::onReadable() {
    notifier_->setEnabled(false);
    char b = 0;
    if (::read(fds_[0], &b, 1) == 1) emit signaled(static_cast<unsigned char>(b));
    notifier_->setEnabled(true);
}
