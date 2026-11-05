#pragma once

#include <QObject>
#include <initializer_list>

class QSocketNotifier;

// Turns POSIX signals (SIGTERM from systemctl stop, SIGINT from Ctrl-C, SIGHUP from a closed terminal) into a Qt signal on the
// event loop, using a socketpair the C handler writes to and a QSocketNotifier reads. Only one
// bridge may exist at a time; the previous handlers come back when it is destroyed.
class SignalBridge : public QObject {
    Q_OBJECT
public:
    explicit SignalBridge(std::initializer_list<int> signos, QObject* parent = nullptr);
    ~SignalBridge() override;

signals:
    void signaled(int signo);

private:
    void onReadable();

    int fds_[2] = {-1, -1};
    QSocketNotifier* notifier_ = nullptr;
    struct Saved;
    Saved* saved_ = nullptr;
};
