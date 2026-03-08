"""
Fantasy Card Game - カード定義モジュール
昔ながらのファンタジー世界をテーマにしたカードたち
"""

import copy
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class CardType(Enum):
    LAND = "土地"
    CREATURE = "クリーチャー"
    SPELL = "呪文"


class Ability(Enum):
    FIRST_STRIKE = "先制攻撃"   # 先にダメージを与える
    DEATHTOUCH = "接死"          # 1ダメージでクリーチャーを破壊
    FLYING = "飛行"              # 飛行クリーチャーのみブロック可
    TRAMPLE = "踏み荒らし"       # 余剰ダメージがプレイヤーへ貫通
    VIGILANCE = "警戒"           # 攻撃してもタップしない
    LIFELINK = "絆魂"            # 与えたダメージ分ライフを得る


_id_counter = 0


def _next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter


@dataclass
class Card:
    template_id: int
    name: str
    card_type: CardType
    description: str
    cost: int = 0
    power: int = 0
    toughness: int = 0
    abilities: List[Ability] = field(default_factory=list)

    # インスタンス固有のゲーム状態
    instance_id: int = field(default_factory=_next_id)
    current_toughness: int = field(init=False)
    is_tapped: bool = field(init=False, default=False)
    summoning_sick: bool = field(init=False, default=True)
    frozen: bool = field(init=False, default=False)  # 石化など

    def __post_init__(self):
        self.current_toughness = self.toughness

    def make_copy(self) -> "Card":
        """デッキ用に新鮮なコピーを作成"""
        c = copy.deepcopy(self)
        c.instance_id = _next_id()
        c.current_toughness = c.toughness
        c.is_tapped = False
        c.summoning_sick = True
        c.frozen = False
        return c

    def can_attack(self) -> bool:
        if self.card_type != CardType.CREATURE:
            return False
        if self.summoning_sick or self.frozen:
            return False
        if Ability.VIGILANCE in self.abilities:
            return True
        return not self.is_tapped

    def can_block(self) -> bool:
        if self.card_type != CardType.CREATURE:
            return False
        return not self.is_tapped and not self.frozen

    @property
    def is_alive(self) -> bool:
        return self.current_toughness > 0

    def has_ability(self, ab: Ability) -> bool:
        return ab in self.abilities

    def untap(self):
        self.is_tapped = False
        self.frozen = False

    def tap(self):
        self.is_tapped = True

    def ability_symbols(self) -> str:
        symbols = {
            Ability.FIRST_STRIKE: "⚔",
            Ability.DEATHTOUCH: "☠",
            Ability.FLYING: "✈",
            Ability.TRAMPLE: "⚡",
            Ability.VIGILANCE: "◎",
            Ability.LIFELINK: "♥",
        }
        return "".join(symbols[a] for a in self.abilities if a in symbols)

    def stats_str(self) -> str:
        if self.card_type == CardType.CREATURE:
            return f"{self.power}/{self.current_toughness}"
        return ""


# ─────────────────────────────────────────────────────────────
# カードテンプレート定義
# ─────────────────────────────────────────────────────────────

def _land(tid, name, desc):
    return Card(template_id=tid, name=name, card_type=CardType.LAND, description=desc)


def _creature(tid, name, cost, power, toughness, desc, abilities=None):
    return Card(
        template_id=tid, name=name, card_type=CardType.CREATURE,
        description=desc, cost=cost, power=power, toughness=toughness,
        abilities=abilities or [],
    )


def _spell(tid, name, cost, desc):
    return Card(template_id=tid, name=name, card_type=CardType.SPELL,
                description=desc, cost=cost)


# ── 土地 (10種) ──────────────────────────────────────────────
LAND_TEMPLATES: List[Card] = [
    _land(1,  "古代の森",     "精霊が宿る、何百年も生きた大木が並ぶ神秘の森。"),
    _land(2,  "神秘の平原",   "光が降り注ぐ聖なる草原。巡礼者が旅の安息を求める。"),
    _land(3,  "影の沼地",     "闇の力が漂う湿地帯。不死者の息吹が充満する。"),
    _land(4,  "竜の峰",       "かつて竜王が君臨した荒々しい山岳地帯。"),
    _land(5,  "水晶の湖",     "透き通る水が輝く神秘の湖。水の精霊が宿る。"),
    _land(6,  "聖なる草原",   "守護神に祝福された広大な平野。英雄伝説の地。"),
    _land(7,  "魔法の洞窟",   "古代魔法師が残した秘術が今も宿る洞窟。"),
    _land(8,  "古代遺跡",     "失われた文明の魔力が染み込んだ廃墟。"),
    _land(9,  "妖精の森",     "妖精が踊り戯れる幻想の森。季節が常に春。"),
    _land(10, "嵐の丘",       "常に雷雨に包まれた魔法の丘。嵐の神の領域。"),
]

# ── クリーチャー (15種) ────────────────────────────────────────
CREATURE_TEMPLATES: List[Card] = [
    _creature(101, "ゴブリンの斥候",   1, 1, 1,
              "小柄だが素早いゴブリンの偵察兵。数の暴力で押し通す。"),
    _creature(102, "骸骨の兵士",       1, 1, 2,
              "不死の呪いで蘇った骸骨の戦士。痛みを感じない。"),
    _creature(103, "エルフの弓使い",   2, 2, 1,
              "精霊の森で鍛えた狙撃の名手。先手必勝が信条。",
              [Ability.FIRST_STRIKE]),
    _creature(104, "癒しの聖職者",     2, 1, 3,
              "傷を癒す祈りを捧げる聖職者。戦いながら仲間を回復する。",
              [Ability.LIFELINK]),
    _creature(105, "ドワーフの戦士",   3, 2, 3,
              "鉄壁の防御と確かな剣技を誇るドワーフ族の精鋭。"),
    _creature(106, "夜明けの騎士",     3, 3, 2,
              "夜明けを告げる聖剣を持つ騎士。先制の一撃が必殺。",
              [Ability.FIRST_STRIKE]),
    _creature(107, "影の暗殺者",       3, 3, 1,
              "闇に潜み一撃で命を奪う暗殺者。毒を纏った短剣を使う。",
              [Ability.DEATHTOUCH]),
    _creature(108, "竜の幼体",         3, 2, 2,
              "まだ幼いが将来有望な竜の子。翼で空を駆ける。",
              [Ability.FLYING]),
    _creature(109, "不死の騎士",       3, 3, 2,
              "死を超えて戦い続ける亡者の騎士。恨みが体を動かす。"),
    _creature(110, "森の番人",         4, 3, 4,
              "古代から森を守護する精霊。眠りながらも戦場を監視する。",
              [Ability.VIGILANCE]),
    _creature(111, "グリフィン",       5, 3, 3,
              "鷹の頭と獅子の体を持つ誇り高き幻獣。天空を支配する。",
              [Ability.FLYING]),
    _creature(112, "海の大蛇",         5, 4, 4,
              "深海に潜む巨大な蛇の怪物。嵐を呼ぶ者とも呼ばれる。"),
    _creature(113, "古代の樹人",       6, 4, 6,
              "何百年も生きた巨大な木の精霊。踏み出す一歩が地響きとなる。",
              [Ability.TRAMPLE]),
    _creature(114, "大地の巨人",       7, 5, 5,
              "大地そのものが形となった古代の巨人。山を割る拳を持つ。",
              [Ability.TRAMPLE]),
    _creature(115, "年老いた竜",       8, 6, 6,
              "数千年を生きた最古の竜。その一息が城壁を溶かす。",
              [Ability.FLYING, Ability.TRAMPLE]),
]

# ── 呪文 (10種) ────────────────────────────────────────────────
SPELL_TEMPLATES: List[Card] = [
    _spell(201, "雷撃",         1, "対象1体に2ダメージを与える。"),
    _spell(202, "死者召喚",     2, "自分の墓地からクリーチャー1体を手札に戻す。"),
    _spell(203, "聖なる光",     2, "自分は6ライフを得る。"),
    _spell(204, "暗黒の呪い",   2, "対象のクリーチャー1体に3ダメージを与える。"),
    _spell(205, "治癒の言葉",   2, "自分は3ライフを得て、カードを1枚引く。"),
    _spell(206, "自然の恵み",   3, "カードを2枚引く。"),
    _spell(207, "火の玉",       3, "対象1体に4ダメージを与える。"),
    _spell(208, "炎の嵐",       4, "相手の全クリーチャーに2ダメージを与える。"),
    _spell(209, "秘術の一撃",   5, "対象1体に6ダメージを与える。"),
    _spell(210, "竜の炎",       4, "対象のクリーチャー1体に5ダメージを与える。"),
]

# 「任意対象」ダメージ呪文のID → ダメージ量
ANY_TARGET_DAMAGE: dict = {201: 2, 207: 4, 209: 6}
# 「クリーチャー対象」ダメージ呪文のID → ダメージ量
CREATURE_TARGET_DAMAGE: dict = {204: 3, 210: 5}


def build_deck() -> List[Card]:
    """
    ランダムな30枚デッキを生成
    構成: 土地12枚 + クリーチャー10枚 + 呪文8枚
    """
    deck: List[Card] = []

    # 土地: ランダムに12枚
    for t in random.choices(LAND_TEMPLATES, k=12):
        deck.append(t.make_copy())

    # クリーチャー: 軽いカードをやや多めに
    weights = [6, 6, 5, 5, 4, 4, 4, 4, 4, 3, 2, 2, 1, 1, 1]
    for t in random.choices(CREATURE_TEMPLATES, weights=weights, k=10):
        deck.append(t.make_copy())

    # 呪文: ランダムに8枚
    for t in random.choices(SPELL_TEMPLATES, k=8):
        deck.append(t.make_copy())

    random.shuffle(deck)
    return deck
