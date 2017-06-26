#!/usr/bin/env python3

import time
import logging as log


def toggle_profiling(clock_type='wall') -> None:
    # https://code.google.com/archive/p/yappi/wikis/usageyappi.wiki
    # https://code.google.com/archive/p/yappi/wikis/UsageYappi_v092.wiki
    import yappi
    if not yappi.is_running():
        yappi.set_clock_type(clock_type)
        yappi.start(builtins=False)
        yappi.profile_begin_time = yappi.get_clock_time()
        yappi.profile_begin_wall_time = time.time()
        log.info(
            'now capturing profiling info of with clock_type=%r',
            yappi.get_clock_type())
    else:
        log.info('stop capturing and output statistics on stdout')
        yappi.stop()
        func_stats = yappi.get_func_stats()
        thread_stats = yappi.get_thread_stats()
        time_yappi = yappi.get_clock_time()
        duration_yappi = time_yappi - yappi.profile_begin_time
        time_wall = time.time()
        duration_wall = time_wall - yappi.profile_begin_wall_time

        yappi.clear_stats()

        print('Profiling time: %s - %s = %.1fs\n' % (
            time.asctime(time.localtime(yappi.profile_begin_wall_time)),
            time.asctime(time.localtime(time_wall)),
            duration_wall,
        ))
        print('yappi duration: %.1fs\n' % duration_yappi)

        func_stats.print_all(
            #out=out,
            columns={0: ("name",  40),
                     1: ("ncall",  5),
                     2: ("tsub",   8),
                     3: ("ttot",   8),
                     4: ("tavg",   8)})
        thread_stats.print_all(
            #out=out,
            columns={0: ("name", 23),
                     1: ("id",    5),
                     2: ("tid",  15),
                     3: ("ttot",  8),
                     4: ("scnt", 10)})

