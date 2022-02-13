import copy
import json
import os
import platform
import queue
import shlex
import subprocess
import threading
import time
import traceback
from typing import Callable, Dict, List, Optional

from kivy.clock import Clock
from kivy.utils import platform as kivy_platform

from katrain.core.constants import (
    OUTPUT_DEBUG,
    OUTPUT_ERROR,
    OUTPUT_EXTRA_DEBUG,
    OUTPUT_KATAGO_STDERR,
    DATA_FOLDER,
    KATAGO_EXCEPTION, OUTPUT_INFO,
)
from katrain.core2.base_katrain2 import KaTrainBase2
from katrain.core2.engine2 import KataGoEngine2
from katrain.core2.game2 import Game
from katrain.core.game_node import GameNode
from katrain.core.lang import i18n
from katrain.core.sgf_parser import Move
from katrain.core.utils import find_package_resource, json_truncate_arrays

#====================run from main=====================================
from katrain.core.constants import (
    OUTPUT_ERROR,
    OUTPUT_KATAGO_STDERR,
    OUTPUT_INFO,
    OUTPUT_DEBUG,
    OUTPUT_EXTRA_DEBUG,
    MODE_ANALYZE,
    HOMEPAGE,
    VERSION,
    STATUS_ERROR,
    STATUS_INFO,
    PLAYING_NORMAL,
    PLAYER_HUMAN,
    SGF_INTERNAL_COMMENTS_MARKER,
    MODE_PLAY,
    DATA_FOLDER,
    AI_DEFAULT,
)

class KaTrainGui(KaTrainBase2):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.message_queue = queue.Queue()

    def start(self):
        dict_conf={
            "katago": "/Users/chengjunjie/Documents/workspace/KataGo/cpp/build/katago",
             "altcommand": "",
              "model": "/Users/chengjunjie/Documents/workspace/KataGo/cpp/build/weights/kata1-best.bin.gz",
              "config": "/Users/chengjunjie/Documents/workspace/KataGo/cpp/build/default_j_gtp.cgf",
              "threads": 12,
              "max_visits": 500,
              "fast_visits": 25,
              "max_time": 8.0,
              "wide_root_noise": 0.04,
              "_enable_ownership": True
        }
        self.engine = KataGoEngine2(self, dict_conf)
        #暂时注释，update ai返回结果
        #threading.Thread(target=self._message_loop_thread, daemon=True).start()

        self.load_sgf_file('/Users/chengjunjie/Documents/test.sgf', fast=True, rewind=True)

    def load_sgf_file(self, file, fast=False, rewind=True):
        self._do_new_game(analyze_fast=fast, sgf_filename=file)

    def _do_new_game(self, move_tree=None, analyze_fast=False, sgf_filename=None):
        self.engine.on_new_game()  # clear queries
        self.game = Game(
            self,
            self.engine,
            move_tree=move_tree,
            analyze_fast=analyze_fast or not move_tree,
            sgf_filename=sgf_filename,
        )
        for bw, player_info in self.players_info.items():
            player_info.sgf_rank = self.game.root.get_property(bw + "R")
            player_info.calculated_rank = None
            if sgf_filename is not None:  # load game->no ai player
                player_info.player_type = PLAYER_HUMAN
                player_info.player_subtype = PLAYING_NORMAL
            self.update_player(bw, player_type=player_info.player_type, player_subtype=player_info.player_subtype)
        #self.controls.graph.initialize_from_game(self.game.root)
        self.update_state(redraw_board=True)

    def update_state(self, redraw_board=False):  # redirect to message queue thread
        self("update_state", redraw_board=redraw_board)

    def __call__(self, message, *args, **kwargs):
        if self.game:
            if message.endswith("popup"):  # gui code needs to run in main kivy thread.
                if self.contributing and "save" not in message and message != "contribute-popup":
                    self.controls.set_status(
                        i18n._("gui-locked").format(action=message), STATUS_INFO, check_level=False
                    )
                    return
                fn = getattr(self, f"_do_{message.replace('-', '_')}")
                Clock.schedule_once(lambda _dt: fn(*args, **kwargs), -1)
            else:  # game related actions
                self.message_queue.put([self.game.game_id, message, args, kwargs])

    def _do_update_state(self, redraw_board=False):
        # is called after every message and on receiving analyses and config changes
        # AI and Trainer/auto-undo handlers
        if not self.game or not self.game.current_node:
            return
        cn = self.game.current_node
        if not self.contributing:
            last_player, next_player = self.players_info[cn.player], self.players_info[cn.next_player]
            if self.play_analyze_mode == MODE_PLAY and self.nav_drawer.state != "open" and self.popup_open is None:
                points_lost = cn.points_lost
                if (
                    last_player.human
                    and cn.analysis_complete
                    and points_lost is not None
                    and points_lost > self.config("trainer/eval_thresholds")[-4]
                ):
                    self.play_mistake_sound(cn)
                teaching_undo = cn.player and last_player.being_taught and cn.parent
                if (
                    teaching_undo
                    and cn.analysis_complete
                    and cn.parent.analysis_complete
                    and not cn.children
                    and not self.game.end_result
                ):
                    self.game.analyze_undo(cn)  # not via message loop
                if (
                    cn.analysis_complete
                    and next_player.ai
                    and not cn.children
                    and not self.game.end_result
                    and not (teaching_undo and cn.auto_undo is None)
                ):  # cn mismatch stops this if undo fired. avoid message loop here or fires repeatedly.
                    self._do_ai_move(cn)
                    Clock.schedule_once(self.board_gui.play_stone_sound, 0.25)
            if self.engine.is_idle() and self.idle_analysis:
                self("analyze-extra", "extra", continuous=True)
        Clock.schedule_once(lambda _dt: self.update_gui(cn, redraw_board=redraw_board), -1)  # trigger?

    def log(self, message, level=OUTPUT_INFO):
        print(message)

    def _message_loop_thread(self):
        while True:
            #game, msg, args, kwargs = self.message_queue.get()
            msg='update_state'
            try:
                fn = getattr(self, f"_do_{msg}")
                fn()  #_do_update_state
            except Exception as exc:
                self.log(f"Exception in processing message {msg} {args}: {exc}", OUTPUT_ERROR)
                traceback.print_exc()

class KaTrainApp:
    def __init__(self):
        self.gui = KaTrainGui()

    def on_start(self):
        self.gui.start()

if __name__ == "__main__":
    app = KaTrainApp()
    app.on_start()

    # #后台三个线程跑
    time.sleep(100000)