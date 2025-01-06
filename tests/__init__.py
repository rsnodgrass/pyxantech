import os
import pty
import threading


def create_dummy_port(responses):
    def listener(port):
        # continuously listen to commands on the master device
        while 1:
            res = b''
            while not res.endswith(b'\r'):
                # keep reading one byte at a time until we have a full line
                res += os.read(port, 1)
            print('command: %s' % res)

            # write back the response
            if res in responses:
                resp = responses[res]
                del responses[res]
                os.write(port, resp)

    master, slave = pty.openpty()
    thread = threading.Thread(target=listener, args=[master], daemon=True)
    thread.start()
    return os.ttyname(slave)
