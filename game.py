"""
Fantasy Card Game - ゲームエンジン
MtGライクなターン制カードバトル (プレイヤー vs CPU)
"""

import random
import time
from typing import Dict, List, Optional, Tuple

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from cards import (
    ANY_TARGET_DAMAGE,
    CREATURE_TARGET_DAMAGE,
    Ability,
    Card,
    CardType,
    build_deck,
)

console = Console()

# ─────────────────────────────────────────────────────────────
# 表示ユーティリティ
# ─────────────────────────────────────────────────────────────

CARD_COLOR = {
    CardType.LAND: "green",
    CardType.CREATURE: "cyan",
    CardType.SPELL: "magenta",
}


def hp_bar(current: int, maximum: int = 20, width: int = 18) -> str:
    ratio = max(0.0, current / maximum)
    filled = round(width * ratio)
    bar = "█" * filled + "░" * (width - filled)
    if ratio > 0.5:
        color = "green"
    elif ratio > 0.25:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{bar}[/{color}]"


def mana_pips(current: int, total: int) -> str:
    return f"[blue]{'◆' * current}{'◇' * (total - current)}[/blue]"


def fmt_creature_on_field(card: Card) -> str:
    """戦場のクリーチャーを1行で表示"""
    syms = card.ability_symbols()
    tap_mark = "[dim]⊘[/dim]" if card.is_tapped else " "
    sick_mark = "[dim]★[/dim]" if card.summoning_sick else " "
    color = CARD_COLOR[card.card_type]
    return (
        f"{tap_mark}{sick_mark}"
        f"[{color}]{card.name}[/{color}]"
        f"[bold] {card.power}/{card.current_toughness}[/bold]"
        f"{syms}"
    )


def fmt_land_on_field(card: Card) -> str:
    tap_mark = "[dim]⊘[/dim]" if card.is_tapped else " "
    return f"{tap_mark}[green]{card.name}[/green]"


def fmt_hand_card(card: Card, index: int, mana_available: int = 99) -> str:
    """手札のカードを整形して表示"""
    color = CARD_COLOR[card.card_type]
    affordable = card.cost <= mana_available if card.card_type != CardType.LAND else True
    dim = "" if affordable else "[dim]"
    end_dim = "" if affordable else "[/dim]"

    if card.card_type == CardType.LAND:
        return f"  [{index}] {dim}[{color}]{card.name}[/{color}] [dim](土地)[/dim]{end_dim}"
    elif card.card_type == CardType.CREATURE:
        syms = card.ability_symbols()
        ab_text = ""
        if card.abilities:
            ab_text = " [dim]" + "・".join(a.value for a in card.abilities) + "[/dim]"
        return (
            f"  [{index}] {dim}[{color}]{card.name}[/{color}]"
            f" [dim]クリーチャー {card.power}/{card.toughness}"
            f" コスト:{card.cost}[/dim]{syms}{ab_text}{end_dim}\n"
            f"       [italic dim]{card.description}[/italic dim]"
        )
    else:
        return (
            f"  [{index}] {dim}[{color}]{card.name}[/{color}]"
            f" [dim]呪文 コスト:{card.cost}[/dim]{end_dim}\n"
            f"       [italic dim]{card.description}[/italic dim]"
        )


# ─────────────────────────────────────────────────────────────
# Player クラス
# ─────────────────────────────────────────────────────────────

class Player:
    def __init__(self, name: str, is_human: bool):
        self.name = name
        self.is_human = is_human
        self.life: int = 20
        self.deck: List[Card] = []
        self.hand: List[Card] = []
        self.battlefield: List[Card] = []
        self.graveyard: List[Card] = []
        self.lands_played_this_turn: int = 0

    def setup(self):
        self.deck = build_deck()
        self.draw_cards(5)

    def draw_cards(self, n: int = 1) -> List[Card]:
        drawn = []
        for _ in range(n):
            if not self.deck:
                break
            card = self.deck.pop(0)
            self.hand.append(card)
            drawn.append(card)
        return drawn

    # ── 戦場のカード分類 ──
    def lands(self) -> List[Card]:
        return [c for c in self.battlefield if c.card_type == CardType.LAND]

    def creatures(self) -> List[Card]:
        return [c for c in self.battlefield if c.card_type == CardType.CREATURE]

    # ── マナ管理 ──
    def available_mana(self) -> int:
        return sum(1 for c in self.lands() if not c.is_tapped)

    def total_mana(self) -> int:
        return len(self.lands())

    def spend_mana(self, amount: int) -> bool:
        untapped = [c for c in self.lands() if not c.is_tapped]
        if len(untapped) < amount:
            return False
        for c in untapped[:amount]:
            c.tap()
        return True

    # ── カードをプレイ ──
    def play_land(self, card: Card) -> bool:
        if self.lands_played_this_turn > 0:
            return False
        if card not in self.hand or card.card_type != CardType.LAND:
            return False
        self.hand.remove(card)
        card.is_tapped = False
        card.summoning_sick = False
        self.battlefield.append(card)
        self.lands_played_this_turn += 1
        return True

    def cast_creature(self, card: Card) -> bool:
        if card not in self.hand or card.card_type != CardType.CREATURE:
            return False
        if not self.spend_mana(card.cost):
            return False
        self.hand.remove(card)
        card.summoning_sick = True
        self.battlefield.append(card)
        return True

    def cast_spell(self, card: Card) -> bool:
        if card not in self.hand or card.card_type != CardType.SPELL:
            return False
        if not self.spend_mana(card.cost):
            return False
        self.hand.remove(card)
        self.graveyard.append(card)
        return True

    # ── 戦闘 ──
    def attackers(self) -> List[Card]:
        return [c for c in self.creatures() if c.can_attack()]

    def blockers(self) -> List[Card]:
        return [c for c in self.creatures() if c.can_block()]

    def has_flyer(self) -> bool:
        return any(c.has_ability(Ability.FLYING) for c in self.creatures())

    # ── アンタップ ──
    def untap_all(self):
        for c in self.battlefield:
            c.untap()
            if c.card_type == CardType.CREATURE:
                c.summoning_sick = False
        self.lands_played_this_turn = 0

    # ── 死亡クリーチャーを墓地へ ──
    def remove_dead(self) -> List[Card]:
        dead = [c for c in self.creatures() if not c.is_alive]
        for c in dead:
            self.battlefield.remove(c)
            self.graveyard.append(c)
        return dead

    def has_playable_land(self) -> bool:
        return (self.lands_played_this_turn == 0 and
                any(c.card_type == CardType.LAND for c in self.hand))

    def playable_non_lands(self) -> List[Card]:
        mana = self.available_mana()
        return [c for c in self.hand
                if c.card_type != CardType.LAND and c.cost <= mana]


# ─────────────────────────────────────────────────────────────
# CPU AI
# ─────────────────────────────────────────────────────────────

class CpuAI:
    def __init__(self, cpu: Player, opponent: Player):
        self.cpu = cpu
        self.opponent = opponent

    def choose_land(self) -> Optional[Card]:
        lands = [c for c in self.cpu.hand if c.card_type == CardType.LAND]
        return lands[0] if lands else None

    def choose_card_to_play(self) -> Optional[Card]:
        """最もコストの高い（インパクトの大きい）カードをプレイ"""
        playable = self.cpu.playable_non_lands()
        if not playable:
            return None
        return max(playable, key=lambda c: c.cost)

    def choose_attackers(self) -> List[Card]:
        """全攻撃可能クリーチャーで攻撃（デフォルト戦略）"""
        return self.cpu.attackers()

    def choose_blockers(self, attackers: List[Card]) -> Dict[int, Optional[Card]]:
        """各攻撃者に対して最適なブロッカーを割り当て"""
        available = list(self.cpu.blockers())
        assignments: Dict[int, Optional[Card]] = {}

        for atk in attackers:
            blk = self._best_blocker(atk, available)
            assignments[atk.instance_id] = blk
            if blk:
                available.remove(blk)

        return assignments

    def _best_blocker(self, atk: Card, available: List[Card]) -> Optional[Card]:
        if not available:
            return None

        # 飛行クリーチャーは飛行クリーチャーのみブロック可能
        if atk.has_ability(Ability.FLYING):
            eligible = [b for b in available if b.has_ability(Ability.FLYING)]
        else:
            eligible = list(available)

        if not eligible:
            return None

        # 有利トレード: ブロッカーが生き残り、攻撃者を倒せる
        for b in eligible:
            atk_dies = self._dies(atk, b)
            b_dies = self._dies(b, atk)
            if atk_dies and not b_dies:
                return b

        # 相打ち: 攻撃者の方が価値が高い場合
        for b in eligible:
            atk_dies = self._dies(atk, b)
            b_dies = self._dies(b, atk)
            if atk_dies and b_dies and atk.cost >= b.cost:
                return b

        # 致死ダメージを防ぐために必要ならブロック
        total_atk = sum(a.power for a in attackers_from_list(atk, available))
        if self.cpu.life <= total_atk + atk.power:
            return min(eligible, key=lambda c: c.power)

        return None

    def _dies(self, defender: Card, attacker: Card) -> bool:
        if attacker.has_ability(Ability.DEATHTOUCH):
            return True
        return attacker.power >= defender.current_toughness

    def choose_spell_target(
        self, spell: Card
    ) -> Tuple[Optional[Player], Optional[Card]]:
        """ダメージ呪文のターゲットを選択"""
        tid = spell.template_id

        if tid in ANY_TARGET_DAMAGE:
            dmg = ANY_TARGET_DAMAGE[tid]
            # 相手プレイヤーに致死ダメージ?
            if self.opponent.life <= dmg:
                return self.opponent, None
            # 高パワークリーチャーを倒せる?
            killable = [c for c in self.opponent.creatures()
                        if c.current_toughness <= dmg]
            if killable:
                return None, max(killable, key=lambda c: c.power)
            # それ以外はプレイヤーを狙う
            return self.opponent, None

        elif tid in CREATURE_TARGET_DAMAGE:
            dmg = CREATURE_TARGET_DAMAGE[tid]
            targets = self.opponent.creatures()
            if not targets:
                return None, None
            killable = [c for c in targets if c.current_toughness <= dmg]
            if killable:
                return None, max(killable, key=lambda c: c.power)
            # 倒せなくても最も強いクリーチャーを弱体化
            return None, max(targets, key=lambda c: c.power)

        return None, None

    def choose_graveyard_creature(self) -> Optional[Card]:
        """死者召喚: 墓地から最も強いクリーチャーを選ぶ"""
        creatures_in_gy = [c for c in self.cpu.graveyard
                           if c.card_type == CardType.CREATURE]
        if not creatures_in_gy:
            return None
        return max(creatures_in_gy, key=lambda c: c.cost)


def attackers_from_list(atk: Card, others: List[Card]) -> List[Card]:
    """ダミーヘルパー: 致死チェック用の攻撃者リスト"""
    return [atk]


# ─────────────────────────────────────────────────────────────
# GameEngine (メインゲームループ)
# ─────────────────────────────────────────────────────────────

class GameEngine:
    def __init__(self):
        self.player = Player("あなた", is_human=True)
        self.cpu = Player("CPU", is_human=False)
        self.ai = CpuAI(self.cpu, self.player)
        self.turn: int = 0
        self.game_over: bool = False
        self.winner: Optional[str] = None
        self.log: List[str] = []

    # ─── セットアップ ──────────────────────────────────────────

    def setup(self):
        self.player.setup()
        self.cpu.setup()

    # ─── ログ ──────────────────────────────────────────────────

    def log_msg(self, msg: str):
        self.log.append(msg)

    # ─── メインループ ──────────────────────────────────────────

    def run(self):
        self.setup()
        self._show_welcome()

        first = True
        is_player_turn = True

        while not self.game_over:
            self.turn += 1
            self.log = []

            if is_player_turn:
                self._player_turn(skip_draw=first)
                first = False
            else:
                self._cpu_turn()

            self._check_win()
            if self.game_over:
                break
            is_player_turn = not is_player_turn

        self._show_game_over()

    # ─── プレイヤーのターン ────────────────────────────────────

    def _player_turn(self, skip_draw: bool = False):
        # アンタップ
        self.player.untap_all()
        console.print(Rule(f"[bold yellow] ターン {self.turn} ─ あなたのターン [/bold yellow]"))

        # ドロー
        if skip_draw:
            console.print("[dim]（先手1ターン目はドローなし）[/dim]\n")
        else:
            drawn = self.player.draw_cards(1)
            if drawn:
                color = CARD_COLOR[drawn[0].card_type]
                console.print(f"[dim]▶ ドロー:[/dim] [{color}]{drawn[0].name}[/{color}]\n")
            else:
                console.print("[red]デッキが空！カードを引けない。[/red]\n")

        # メインフェーズ
        self._player_main_phase()

        # 戦闘フェーズ
        self._player_combat_phase()

        # エンドフェーズ
        console.print(Rule("[dim]ターン終了[/dim]"))
        console.print()

    # ── メインフェーズ（プレイヤー）───────────────────────────

    def _player_main_phase(self):
        while True:
            self._display_game_state()
            self._display_hand()

            mana = self.player.available_mana()
            total = self.player.total_mana()
            can_land = self.player.has_playable_land()
            can_play = bool(self.player.playable_non_lands())

            console.print(
                f"\nマナ: {mana_pips(mana, total)} [dim]{mana}/{total}[/dim]"
                f"  手札: [bold]{len(self.player.hand)}枚[/bold]"
            )
            console.print("\n[bold]アクションを選んでください:[/bold]")
            options = []
            if can_land or can_play:
                options.append("[1] カードをプレイ")
            options.append("[2] 戦闘フェーズへ")
            options.append("[3] ターン終了")
            for o in options:
                console.print(f"  {o}")

            choice = self._input("> ").strip()

            if choice == "1" and (can_land or can_play):
                self._player_play_card()
            elif choice == "2":
                break
            elif choice == "3":
                # 戦闘をスキップしてターン終了
                return
            elif choice == "1":
                console.print("[red]今はプレイできるカードがありません。[/red]")

    def _player_play_card(self):
        """手札からカードを選んでプレイ"""
        mana = self.player.available_mana()
        hand = self.player.hand

        console.print("\n[bold]手札:[/bold]")
        for i, card in enumerate(hand, 1):
            if card.card_type == CardType.LAND:
                if self.player.lands_played_this_turn == 0:
                    console.print(fmt_hand_card(card, i, mana))
                else:
                    console.print(f"  [{i}] [dim]{card.name} (土地 ─ 今ターンは使用済み)[/dim]")
            else:
                console.print(fmt_hand_card(card, i, mana))

        console.print("  [0] キャンセル")
        choice = self._input("カード番号> ").strip()

        if not choice.isdigit():
            return
        idx = int(choice) - 1
        if idx < 0 or idx >= len(hand):
            return

        card = hand[idx]

        if card.card_type == CardType.LAND:
            if self.player.lands_played_this_turn > 0:
                console.print("[red]土地は1ターンに1枚しかプレイできません。[/red]")
                return
            if self.player.play_land(card):
                console.print(f"[green]▶ 土地をプレイ:[/green] {card.name}")
        elif card.card_type == CardType.CREATURE:
            if card.cost > mana:
                console.print(f"[red]マナが足りません。(必要:{card.cost} / 現在:{mana})[/red]")
                return
            if self.player.cast_creature(card):
                console.print(f"[cyan]▶ 召喚:[/cyan] {card.name} ({card.power}/{card.toughness})")
        else:  # SPELL
            if card.cost > mana:
                console.print(f"[red]マナが足りません。(必要:{card.cost} / 現在:{mana})[/red]")
                return
            if self.player.cast_spell(card):
                self._resolve_spell_player(card)

    # ── 戦闘フェーズ（プレイヤー）────────────────────────────

    def _player_combat_phase(self):
        atk_candidates = self.player.attackers()
        if not atk_candidates:
            return

        console.print(Rule("[bold red]⚔ 戦闘フェーズ[/bold red]"))
        console.print("\n[bold]攻撃するクリーチャーを選んでください[/bold]")
        console.print("[dim](番号を入力してトグル, 空Enterで確定)[/dim]\n")

        selected: List[Card] = []

        while True:
            for i, c in enumerate(atk_candidates, 1):
                mark = "[green]✓[/green]" if c in selected else " "
                console.print(f"  [{i}] {mark} {fmt_creature_on_field(c)}")
            console.print("  [0] 攻撃しない（終了）")

            choice = self._input("選択> ").strip()
            if choice == "" or choice == "0":
                break
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(atk_candidates):
                    c = atk_candidates[idx]
                    if c in selected:
                        selected.remove(c)
                    else:
                        selected.append(c)

        if not selected:
            console.print("[dim]攻撃なし[/dim]\n")
            return

        # 攻撃者タップ (VIGILANCE除く)
        for c in selected:
            if not c.has_ability(Ability.VIGILANCE):
                c.tap()

        console.print(f"\n[bold red]攻撃![/bold red] ", end="")
        names = "、".join(c.name for c in selected)
        console.print(f"{names}")

        # CPUがブロッカーを選ぶ
        time.sleep(0.6)
        assignments = self.ai.choose_blockers(selected)

        # ブロック宣言表示
        has_blocker = False
        for atk in selected:
            blk = assignments.get(atk.instance_id)
            if blk:
                has_blocker = True
                console.print(f"[yellow]  CPU: {blk.name} ({blk.power}/{blk.current_toughness}) が {atk.name} をブロック！[/yellow]")

        if not has_blocker:
            console.print("[dim]CPUはブロックしない[/dim]")

        time.sleep(0.5)

        # 戦闘解決
        for atk in selected:
            blk = assignments.get(atk.instance_id)
            self._resolve_combat(atk, blk, self.player, self.cpu)

        # 死亡処理
        p_dead = self.player.remove_dead()
        c_dead = self.cpu.remove_dead()
        for c in p_dead:
            console.print(f"[red]  {c.name} が死亡 → 墓地へ[/red]")
        for c in c_dead:
            console.print(f"[green]  CPU の {c.name} が死亡 → 墓地へ[/green]")

        console.print()

    # ─── CPUのターン ───────────────────────────────────────────

    def _cpu_turn(self):
        self.cpu.untap_all()
        console.print(Rule("[bold purple] CPUのターン [/bold purple]"))
        time.sleep(0.4)

        # ドロー
        drawn = self.cpu.draw_cards(1)
        if drawn:
            console.print(f"[dim]CPU がカードを1枚引いた[/dim]")
        else:
            console.print("[red]CPU のデッキが空！[/red]")

        time.sleep(0.3)

        # メインフェーズ: 土地プレイ
        land = self.ai.choose_land()
        if land and self.cpu.lands_played_this_turn == 0:
            self.cpu.play_land(land)
            console.print(f"[green]CPU: 土地をプレイ →[/green] {land.name}")
            time.sleep(0.3)

        # メインフェーズ: カードを連続プレイ
        while True:
            card = self.ai.choose_card_to_play()
            if not card:
                break
            if card.card_type == CardType.CREATURE:
                self.cpu.cast_creature(card)
                console.print(f"[cyan]CPU: 召喚 →[/cyan] {card.name} ({card.power}/{card.toughness})")
            else:
                self.cpu.cast_spell(card)
                self._resolve_spell_cpu(card)
            time.sleep(0.5)

        # 戦闘フェーズ
        self._cpu_combat_phase()

        console.print(Rule("[dim]CPU のターン終了[/dim]"))
        time.sleep(0.3)
        console.print()

    def _cpu_combat_phase(self):
        attackers = self.ai.choose_attackers()
        if not attackers:
            return

        console.print(Rule("[bold red]⚔ CPU の攻撃![/bold red]"))
        names = "、".join(f"{c.name}({c.power}/{c.current_toughness})" for c in attackers)
        console.print(f"[bold red]CPU の攻撃:[/bold red] {names}")
        time.sleep(0.5)

        # 攻撃者タップ
        for c in attackers:
            if not c.has_ability(Ability.VIGILANCE):
                c.tap()

        # プレイヤーはブロッカーを選ぶ
        console.print("\n[bold]ブロッカーを選んでください[/bold]")
        console.print("[dim](各攻撃者に対してブロッカーを1体割り当てます)[/dim]\n")

        blockers_available = list(self.player.blockers())
        assignments: Dict[int, Optional[Card]] = {}

        for atk in attackers:
            assignments[atk.instance_id] = None

            # 飛行持ちはブロック不可（飛行クリーチャー以外）
            if atk.has_ability(Ability.FLYING):
                eligible = [b for b in blockers_available if b.has_ability(Ability.FLYING)]
            else:
                eligible = list(blockers_available)

            if not eligible:
                console.print(
                    f"  [red]{atk.name} ({atk.power}/{atk.current_toughness})[/red]"
                    f"{'[dim] ✈飛行[/dim]' if atk.has_ability(Ability.FLYING) else ''}"
                    f" → ブロック不可"
                )
                continue

            console.print(
                f"\n  [red]{atk.name} ({atk.power}/{atk.current_toughness})[/red]"
                f"{'[dim] ✈飛行[/dim]' if atk.has_ability(Ability.FLYING) else ''}"
                f" をブロックするクリーチャーを選ぶ:"
            )
            console.print("    [0] ブロックしない")
            for i, b in enumerate(eligible, 1):
                console.print(f"    [{i}] {fmt_creature_on_field(b)}")

            choice = self._input("  > ").strip()
            if choice.isdigit() and int(choice) >= 1:
                idx = int(choice) - 1
                if 0 <= idx < len(eligible):
                    blk = eligible[idx]
                    assignments[atk.instance_id] = blk
                    blockers_available.remove(blk)
                    console.print(f"    [green]{blk.name} がブロック！[/green]")

        time.sleep(0.3)
        console.print()

        # 戦闘解決
        for atk in attackers:
            blk = assignments.get(atk.instance_id)
            self._resolve_combat(atk, blk, self.cpu, self.player)

        # 死亡処理
        c_dead = self.cpu.remove_dead()
        p_dead = self.player.remove_dead()
        for c in c_dead:
            console.print(f"[green]  CPU の {c.name} が死亡 → 墓地へ[/green]")
        for c in p_dead:
            console.print(f"[red]  あなたの {c.name} が死亡 → 墓地へ[/red]")

        console.print()

    # ─── 戦闘解決 ─────────────────────────────────────────────

    def _resolve_combat(
        self,
        atk: Card,
        blk: Optional[Card],
        atk_owner: Player,
        def_owner: Player,
    ):
        if blk is None:
            # ブロックなし → プレイヤーにダメージ
            dmg = atk.power
            def_owner.life -= dmg
            lifelink = atk.has_ability(Ability.LIFELINK)
            trample_str = ""
            if lifelink:
                atk_owner.life += dmg
            console.print(
                f"  [bold]{atk.name}[/bold] が [bold]{def_owner.name}[/bold] に"
                f" [red]{dmg}[/red] ダメージ！"
                f"{'（絆魂: +' + str(dmg) + 'ライフ）' if lifelink else ''}"
            )
        else:
            # ブロックあり → 戦闘ダメージ解決
            self._resolve_blocked_combat(atk, blk, atk_owner)

    def _resolve_blocked_combat(self, atk: Card, blk: Card, atk_owner: Player):
        first_strike_atk = atk.has_ability(Ability.FIRST_STRIKE)
        first_strike_blk = blk.has_ability(Ability.FIRST_STRIKE)
        deathtouch_atk = atk.has_ability(Ability.DEATHTOUCH)
        deathtouch_blk = blk.has_ability(Ability.DEATHTOUCH)
        lifelink_atk = atk.has_ability(Ability.LIFELINK)
        lifelink_blk = blk.has_ability(Ability.LIFELINK)
        trample_atk = atk.has_ability(Ability.TRAMPLE)

        console.print(
            f"  [bold]{atk.name}[/bold] ({atk.power}/{atk.current_toughness})"
            f" vs [bold]{blk.name}[/bold] ({blk.power}/{blk.current_toughness})"
        )

        if first_strike_atk and not first_strike_blk:
            # 先制攻撃: 攻撃者が先にダメージ
            self._deal_damage(atk, blk, atk_owner, lifelink_atk, deathtouch_atk)
            console.print(f"    [yellow]先制攻撃![/yellow]")
            if not blk.is_alive:
                console.print(f"    {blk.name} は先制攻撃で倒された！")
                return
            # ブロッカーも反撃
            self._deal_damage(blk, atk, None, lifelink_blk, deathtouch_blk)
        elif first_strike_blk and not first_strike_atk:
            # ブロッカーが先制攻撃
            self._deal_damage(blk, atk, None, lifelink_blk, deathtouch_blk)
            console.print(f"    [yellow]{blk.name} の先制攻撃![/yellow]")
            if not atk.is_alive:
                console.print(f"    {atk.name} は先制攻撃で倒された！")
                return
            self._deal_damage(atk, blk, atk_owner, lifelink_atk, deathtouch_atk)
        else:
            # 通常: 同時ダメージ
            atk_dmg = atk.power
            blk_dmg = blk.power

            # ダメージを適用（同時）
            if deathtouch_atk:
                blk.current_toughness = 0
            else:
                blk.current_toughness -= atk_dmg

            if deathtouch_blk:
                atk.current_toughness = 0
            else:
                atk.current_toughness -= blk_dmg

            if lifelink_atk:
                atk_owner.life += atk_dmg
            if lifelink_blk and self._other_owner(atk_owner):
                pass  # ブロッカーオーナーのライフ回復（簡略化: 省略）

            # 踏み荒らし
            if trample_atk and not blk.is_alive:
                excess = atk_dmg - blk.toughness
                if excess > 0:
                    opp = self._opponent_of(atk_owner)
                    opp.life -= excess
                    console.print(f"    [bold]踏み荒らし![/bold] {opp.name} に {excess} ダメージ！")

            console.print(
                f"    {atk.name} → {blk.name} に [red]{atk_dmg}[/red] ダメージ"
                f"{'（絆魂）' if lifelink_atk else ''}"
            )
            console.print(
                f"    {blk.name} → {atk.name} に [red]{blk_dmg}[/red] ダメージ"
            )

    def _deal_damage(
        self,
        dealer: Card,
        target: Card,
        dealer_owner: Optional[Player],
        lifelink: bool,
        deathtouch: bool,
    ):
        dmg = dealer.power
        if deathtouch:
            target.current_toughness = 0
        else:
            target.current_toughness -= dmg
        if lifelink and dealer_owner:
            dealer_owner.life += dmg
        console.print(
            f"    {dealer.name} → {target.name} に [red]{dmg}[/red] ダメージ"
            f"{'（接死）' if deathtouch else ''}{'（絆魂）' if lifelink else ''}"
        )

    def _opponent_of(self, owner: Player) -> Player:
        return self.cpu if owner is self.player else self.player

    def _other_owner(self, owner: Optional[Player]) -> Optional[Player]:
        if owner is None:
            return None
        return self._opponent_of(owner)

    # ─── 呪文解決 ─────────────────────────────────────────────

    def _resolve_spell_player(self, spell: Card):
        """プレイヤーが使った呪文の効果を解決"""
        tid = spell.template_id

        if tid in ANY_TARGET_DAMAGE:
            dmg = ANY_TARGET_DAMAGE[tid]
            console.print(f"\n[magenta]{spell.name}[/magenta] を発動！ (最大{dmg}ダメージ)")
            target_p, target_c = self._player_choose_any_target(dmg)
            if target_p:
                target_p.life -= dmg
                console.print(f"  → {target_p.name} に {dmg} ダメージ！ (残: {target_p.life} HP)")
            elif target_c:
                target_c.current_toughness -= dmg
                console.print(f"  → {target_c.name} に {dmg} ダメージ！ ({target_c.current_toughness} HP残)")
                self.cpu.remove_dead()

        elif tid in CREATURE_TARGET_DAMAGE:
            dmg = CREATURE_TARGET_DAMAGE[tid]
            console.print(f"\n[magenta]{spell.name}[/magenta] を発動！ ({dmg}ダメージ)")
            target_c = self._player_choose_creature_target(dmg)
            if target_c:
                target_c.current_toughness -= dmg
                console.print(f"  → {target_c.name} に {dmg} ダメージ！ ({target_c.current_toughness} HP残)")
                self.cpu.remove_dead()
                self.player.remove_dead()

        elif tid == 202:  # 死者召喚
            console.print(f"\n[magenta]{spell.name}[/magenta] を発動！")
            creatures_in_gy = [c for c in self.player.graveyard if c.card_type == CardType.CREATURE]
            if not creatures_in_gy:
                console.print("  墓地にクリーチャーがいない。")
            else:
                console.print("  墓地のクリーチャー:")
                for i, c in enumerate(creatures_in_gy, 1):
                    console.print(f"    [{i}] {c.name} ({c.power}/{c.toughness})")
                console.print("  [0] キャンセル")
                ch = self._input("  > ").strip()
                if ch.isdigit() and 1 <= int(ch) <= len(creatures_in_gy):
                    chosen = creatures_in_gy[int(ch) - 1]
                    chosen.make_copy()  # リセット
                    self.player.graveyard.remove(chosen)
                    chosen.current_toughness = chosen.toughness
                    chosen.is_tapped = False
                    chosen.summoning_sick = True
                    self.player.hand.append(chosen)
                    console.print(f"  → {chosen.name} を手札に戻した！")

        elif tid == 203:  # 聖なる光
            gain = 6
            self.player.life += gain
            console.print(f"\n[magenta]{spell.name}[/magenta]！ +{gain} ライフ (現在: {self.player.life} HP)")

        elif tid == 204:  # 暗黒の呪い → クリーチャーに3ダメージ
            dmg = 3
            console.print(f"\n[magenta]{spell.name}[/magenta] を発動！ (クリーチャーに{dmg}ダメージ)")
            target_c = self._player_choose_creature_target(dmg)
            if target_c:
                target_c.current_toughness -= dmg
                console.print(f"  → {target_c.name} に {dmg} ダメージ！ ({target_c.current_toughness} HP残)")
                self.cpu.remove_dead()
                self.player.remove_dead()

        elif tid == 205:  # 治癒の言葉
            gain = 3
            self.player.life += gain
            drawn = self.player.draw_cards(1)
            console.print(f"\n[magenta]{spell.name}[/magenta]！ +{gain} ライフ", end="")
            if drawn:
                color = CARD_COLOR[drawn[0].card_type]
                console.print(f" / [{color}]{drawn[0].name}[/{color}] をドロー")
            else:
                console.print(" (デッキ切れ)")

        elif tid == 206:  # 自然の恵み
            drawn = self.player.draw_cards(2)
            console.print(f"\n[magenta]{spell.name}[/magenta]！ カードを{len(drawn)}枚引いた。")

        elif tid == 208:  # 炎の嵐
            dmg = 2
            console.print(f"\n[magenta]{spell.name}[/magenta]！ CPU の全クリーチャーに {dmg} ダメージ！")
            for c in list(self.cpu.creatures()):
                c.current_toughness -= dmg
                console.print(f"  → {c.name} に {dmg} ダメージ ({c.current_toughness} HP残)")
            self.cpu.remove_dead()

    def _resolve_spell_cpu(self, spell: Card):
        """CPUが使った呪文の効果を解決"""
        tid = spell.template_id

        if tid in ANY_TARGET_DAMAGE:
            dmg = ANY_TARGET_DAMAGE[tid]
            target_p, target_c = self.ai.choose_spell_target(spell)
            if target_p:
                target_p.life -= dmg
                console.print(
                    f"[magenta]CPU: {spell.name}[/magenta] → "
                    f"{target_p.name} に {dmg} ダメージ！ (残: {target_p.life} HP)"
                )
            elif target_c:
                target_c.current_toughness -= dmg
                console.print(
                    f"[magenta]CPU: {spell.name}[/magenta] → "
                    f"{target_c.name} に {dmg} ダメージ！ ({target_c.current_toughness} HP残)"
                )
                self.player.remove_dead()
                self.cpu.remove_dead()

        elif tid in CREATURE_TARGET_DAMAGE:
            dmg = CREATURE_TARGET_DAMAGE[tid]
            _, target_c = self.ai.choose_spell_target(spell)
            if target_c:
                target_c.current_toughness -= dmg
                console.print(
                    f"[magenta]CPU: {spell.name}[/magenta] → "
                    f"{target_c.name} に {dmg} ダメージ！ ({target_c.current_toughness} HP残)"
                )
                self.player.remove_dead()
                self.cpu.remove_dead()
            else:
                console.print(f"[magenta]CPU: {spell.name}[/magenta] → 対象なし")

        elif tid == 202:  # 死者召喚
            chosen = self.ai.choose_graveyard_creature()
            if chosen:
                self.cpu.graveyard.remove(chosen)
                chosen.current_toughness = chosen.toughness
                chosen.is_tapped = False
                chosen.summoning_sick = True
                self.cpu.hand.append(chosen)
                console.print(f"[magenta]CPU: {spell.name}[/magenta] → {chosen.name} を手札に戻した")
            else:
                console.print(f"[magenta]CPU: {spell.name}[/magenta] → 墓地にクリーチャーなし")

        elif tid == 203:  # 聖なる光
            gain = 6
            self.cpu.life += gain
            console.print(f"[magenta]CPU: {spell.name}[/magenta] → +{gain} ライフ (現在: {self.cpu.life} HP)")

        elif tid == 204:  # 暗黒の呪い
            dmg = 3
            _, target_c = self.ai.choose_spell_target(spell)
            if target_c:
                target_c.current_toughness -= dmg
                console.print(
                    f"[magenta]CPU: {spell.name}[/magenta] → "
                    f"{target_c.name} に {dmg} ダメージ！ ({target_c.current_toughness} HP残)"
                )
                self.player.remove_dead()

        elif tid == 205:  # 治癒の言葉
            gain = 3
            self.cpu.life += gain
            drawn = self.cpu.draw_cards(1)
            console.print(
                f"[magenta]CPU: {spell.name}[/magenta] → "
                f"+{gain} ライフ / カードを{len(drawn)}枚引いた"
            )

        elif tid == 206:  # 自然の恵み
            drawn = self.cpu.draw_cards(2)
            console.print(f"[magenta]CPU: {spell.name}[/magenta] → カードを{len(drawn)}枚引いた")

        elif tid == 208:  # 炎の嵐
            dmg = 2
            console.print(f"[magenta]CPU: {spell.name}[/magenta] → あなたの全クリーチャーに {dmg} ダメージ！")
            for c in list(self.player.creatures()):
                c.current_toughness -= dmg
                console.print(f"  → {c.name} に {dmg} ダメージ ({c.current_toughness} HP残)")
            self.player.remove_dead()

    # ─── ターゲット選択（プレイヤー用）───────────────────────

    def _player_choose_any_target(self, dmg: int) -> Tuple[Optional[Player], Optional[Card]]:
        """任意対象ダメージのターゲットを選ぶ"""
        console.print("  ターゲットを選んでください:")
        console.print(f"  [0] CPU プレイヤー (残: {self.cpu.life} HP)")
        cpu_creatures = self.cpu.creatures()
        for i, c in enumerate(cpu_creatures, 1):
            console.print(f"  [{i}] {c.name} ({c.power}/{c.current_toughness})")
        p_creatures = self.player.creatures()
        offset = len(cpu_creatures)
        for i, c in enumerate(p_creatures, offset + 1):
            console.print(f"  [{i}] [dim]自分の[/dim] {c.name} ({c.power}/{c.current_toughness})")

        choice = self._input("  > ").strip()
        if not choice.isdigit():
            return None, None
        idx = int(choice)
        if idx == 0:
            return self.cpu, None
        elif 1 <= idx <= len(cpu_creatures):
            return None, cpu_creatures[idx - 1]
        else:
            real_idx = idx - offset - 1
            if 0 <= real_idx < len(p_creatures):
                return None, p_creatures[real_idx]
        return None, None

    def _player_choose_creature_target(self, dmg: int) -> Optional[Card]:
        """クリーチャー対象ダメージのターゲットを選ぶ"""
        all_creatures = self.cpu.creatures() + self.player.creatures()
        if not all_creatures:
            console.print("  対象となるクリーチャーがいない。")
            return None
        console.print("  対象クリーチャーを選んでください:")
        cpu_c = self.cpu.creatures()
        player_c = self.player.creatures()
        for i, c in enumerate(cpu_c, 1):
            console.print(f"  [{i}] CPU: {c.name} ({c.power}/{c.current_toughness})")
        offset = len(cpu_c)
        for i, c in enumerate(player_c, offset + 1):
            console.print(f"  [{i}] 自分: {c.name} ({c.power}/{c.current_toughness})")
        console.print("  [0] キャンセル")

        choice = self._input("  > ").strip()
        if not choice.isdigit() or int(choice) == 0:
            return None
        idx = int(choice)
        if 1 <= idx <= len(cpu_c):
            return cpu_c[idx - 1]
        else:
            real_idx = idx - offset - 1
            if 0 <= real_idx < len(player_c):
                return player_c[real_idx]
        return None

    # ─── 勝敗チェック ─────────────────────────────────────────

    def _check_win(self):
        if self.player.life <= 0:
            self.game_over = True
            self.winner = "CPU"
        elif self.cpu.life <= 0:
            self.game_over = True
            self.winner = "あなた"
        elif not self.player.deck and not self.player.hand and not self.player.battlefield:
            self.game_over = True
            self.winner = "CPU"
        elif not self.cpu.deck and not self.cpu.hand and not self.cpu.battlefield:
            self.game_over = True
            self.winner = "あなた"

    # ─── 画面表示 ─────────────────────────────────────────────

    def _display_game_state(self):
        console.print()

        # CPU エリア
        cpu_life_bar = hp_bar(max(0, self.cpu.life))
        cpu_header = (
            f"[bold purple]CPU[/bold purple]  "
            f"{cpu_life_bar} [bold]{self.cpu.life}[/bold]/20 HP  "
            f"[dim]手札:{len(self.cpu.hand)}枚  デッキ:{len(self.cpu.deck)}枚[/dim]"
        )

        cpu_field_parts = []
        for c in self.cpu.lands():
            cpu_field_parts.append(fmt_land_on_field(c))
        for c in self.cpu.creatures():
            cpu_field_parts.append(fmt_creature_on_field(c))

        cpu_field_str = "  ".join(cpu_field_parts) if cpu_field_parts else "[dim](空)[/dim]"
        cpu_content = cpu_header + "\n戦場: " + cpu_field_str

        console.print(Panel(cpu_content, border_style="purple", padding=(0, 1)))

        console.print(Align("⚔  vs  ⚔", align="center"))

        # プレイヤーエリア
        mana = self.player.available_mana()
        total = self.player.total_mana()
        p_life_bar = hp_bar(max(0, self.player.life))
        p_header = (
            f"[bold yellow]あなた[/bold yellow]  "
            f"{p_life_bar} [bold]{self.player.life}[/bold]/20 HP  "
            f"マナ: {mana_pips(mana, total)} {mana}/{total}  "
            f"[dim]デッキ:{len(self.player.deck)}枚[/dim]"
        )

        p_field_parts = []
        for c in self.player.lands():
            p_field_parts.append(fmt_land_on_field(c))
        for c in self.player.creatures():
            p_field_parts.append(fmt_creature_on_field(c))

        p_field_str = "  ".join(p_field_parts) if p_field_parts else "[dim](空)[/dim]"
        p_content = p_header + "\n戦場: " + p_field_str

        console.print(Panel(p_content, border_style="yellow", padding=(0, 1)))

    def _display_hand(self):
        if not self.player.hand:
            console.print("\n[dim]手札: なし[/dim]")
            return
        mana = self.player.available_mana()
        console.print(f"\n[bold]手札 ({len(self.player.hand)}枚):[/bold]")
        for i, card in enumerate(self.player.hand, 1):
            console.print(fmt_hand_card(card, i, mana))

    # ─── ウェルカム / ゲームオーバー ──────────────────────────

    def _show_welcome(self):
        console.clear()
        title = Text()
        title.append("\n⚔  Fantasy Card Battle  ⚔\n", style="bold yellow")
        title.append("  昔ながらのファンタジー世界へようこそ  \n", style="dim")
        console.print(Panel(Align(title, align="center"), border_style="yellow"))

        console.print(
            "\n[bold]ゲームルール:[/bold]\n"
            "  ・各プレイヤーは30枚のランダムデッキを使用\n"
            "  ・初期ライフ: 20\n"
            "  ・土地を置いてマナを生み出し、クリーチャーや呪文を使う\n"
            "  ・相手のライフを0にすれば勝利！\n"
            "\n[dim]★=召喚酔い  ⊘=タップ済み  ✈=飛行  ⚔=先制攻撃\n"
            "☠=接死  ⚡=踏み荒らし  ◎=警戒  ♥=絆魂[/dim]\n"
        )
        self._input("Enterキーでゲーム開始...")
        console.clear()

    def _show_game_over(self):
        console.print()
        if self.winner == "あなた":
            msg = Text("\n🏆  あなたの勝利！  🏆\n", style="bold green")
        else:
            msg = Text("\n💀  CPUの勝利...  💀\n", style="bold red")

        console.print(Panel(
            Align(msg, align="center"),
            border_style="yellow",
            title="Game Over",
        ))
        console.print(
            f"\n[dim]最終ターン数: {self.turn}\n"
            f"あなたの残りライフ: {self.player.life}\n"
            f"CPUの残りライフ: {self.cpu.life}[/dim]\n"
        )

    # ─── 入力ユーティリティ ────────────────────────────────────

    def _input(self, prompt: str = "") -> str:
        try:
            return console.input(prompt)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]ゲームを終了します。[/dim]")
            raise SystemExit(0)
