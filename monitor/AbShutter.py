#!/usr/bin/env python3
#
# (C) Yoichi Tanibayashi

# ToDo
# * callback function

import evdev
import os
import time
import threading
import click

from logging import getLogger, StreamHandler, Formatter, DEBUG, INFO, WARN
logger = getLogger(__name__)
logger.setLevel(DEBUG)
console_handler = StreamHandler()
console_handler.setLevel(DEBUG)
handler_fmt = Formatter(
    '%(asctime)s %(levelname)s %(name)s.%(funcName)s()> %(message)s',
                        datefmt='%H:%M:%S')
console_handler.setFormatter(handler_fmt)
logger.addHandler(console_handler)
logger.propagate = False
def get_logger(name, debug=False):
    l = logger.getChild(name)
    if debug:
        l.setLevel(DEBUG)
    else:
        l.setLevel(INFO)

    return l


#####
class AbShutter(threading.Thread):
    EV_VAL = ('RELEASE', 'PUSH', 'HOLD')
    DEVFILE_PREFIX = '/dev/input/event'

    def __init__(self, name="", dev=-1, cb_func=None, debug=False):
        self.debug = debug
        self.logger = get_logger(__class__.__name__, self.debug)
        self.logger.debug('dev=%d', dev)
        self.logger.debug('dname=%s', name)

        self.dname          = name
        self.dev            = dev
        self.cb_func        = cb_func

        
        if name != "" : self.connect_dname(name)

        self.input_dev_file = self.DEVFILE_PREFIX + str(self.dev)
        if not os.path.exists(self.input_dev_file):
            self.logger.error('no such device: %s', self.input_dev_file)
            raise Exception('no such device : %s' % self.input_dev_file)

        self.logger.debug('input_dev_file=%s', self.input_dev_file)

        self.input_dev      = evdev.device.InputDevice(self.input_dev_file)
        self.logger.info(f'dev_name:{self.input_dev.name} phys:{self.input_dev.phys}')

        super().__init__(daemon=True)


    def connect_dname(self, name) :
        self.logger.debug("connect device ...")
        chk = True
        while chk :
            devs = evdev.util.list_devices()
            for d in devs :
                dd = evdev.device.InputDevice(d)
                if dd.name == name :
                    self.dev = dd.path.replace(self.DEVFILE_PREFIX,'')
                    self.logger.debug(f"device is {self.dev}")
                    chk = False
                    return

            self.logger.debug(f"No such Device {name}... wait 10sec")
            time.sleep(5)


        
    def wait_key_event(self):
        self.logger.debug('')
        
        try : 
            for ev in self.input_dev.read_loop():
                self.logger.debug(ev)
                if ev.type == evdev.events.EV_KEY:
                    break
                self.logger.debug('ignore this event')

        except OSError as e :
            self.logger.debug('Not Coonect Device.. Skip')
            return (-1, -1)
            
        self.logger.debug('(ev.code, ev.value) = %s', (ev.code, ev.value))

        if self.cb_func != None:
            self.cb_func(self.dev, ev.code, ev.value)

        return (ev.code, ev.value)

    def loop(self):
        self.logger.debug('')

        while True:
            (code, value) = self.wait_key_event()
            if code == -1 : 
                ## Restart
                self.connect_dname(self.dname)
                self.input_dev = evdev.device.InputDevice(self.input_dev_file)
                continue

            self.logger.debug('%s(%d) %s(%d)',
                              __class__.keycode2str(code), code, 
                              __class__.val2str(value), value)

    def run(self):
        self.logger.debug('')
        self.loop()


    @classmethod
    def keycode2str(cls, code):
        return evdev.events.keys[code]

    @classmethod
    def val2str(cls, value):
        return cls.EV_VAL[value]

#####
class sample:
    def __init__(self, name="", devs=-1, debug=False):
        self.debug = debug
        self.logger = get_logger(__class__.__name__, self.debug)
        self.logger.debug('devs=%s', str(devs))

        self.name = name
        self.devs = devs

        print(name)


    def main(self):
        self.logger.debug('')
        
        self.objs = []
        for d in self.devs:
            # create 'AbShutter' object and start it
            o = AbShutter(self.name, d, self.sample_cb_func, debug=self.debug)
            o.start()
            self.objs.append(o)
        self.logger.debug(str(self.objs))

        while True:
            print(time.strftime('%Y/%m/%d(%a) %H:%M:%S'))
            time.sleep(10)
            

    # sample callback function
    def sample_cb_func(self, dev, code, value):
        self.logger.debug('')
        
        print('dev=%d, code=%d:%s, value=%d:%s'
              % (dev,
                 code, AbShutter.keycode2str(code),
                 value, AbShutter.val2str(value)))
        

#####
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
@click.command(context_settings=CONTEXT_SETTINGS)
@click.argument('devs', metavar='[0|1|2|4..]...', type=int, nargs=-1)
@click.option('-n','name', type=str, help='device name', default="" )
@click.option('--debug', '-d', 'debug', is_flag=True, default=False, help='debug flag')
def main(name, devs, debug):
    logger.setLevel(INFO)
    if debug:
        logger.setLevel(DEBUG)

    logger.debug('devs=%s', str(devs))
    logger.debug('dname=%s', str(name))

    try:
        sample(name, devs, debug=debug).main()
    finally:
        print('END')

if __name__ == '__main__':
    main()
