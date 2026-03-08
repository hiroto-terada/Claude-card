"""
Fantasy Card Battle
昔ながらのファンタジー世界をテーマにした MtG ライクカードゲーム
プレイヤー vs CPU  /  ランダムデッキ

使い方:
    python main.py
"""

from game import GameEngine


def main():
    engine = GameEngine()
    engine.run()


if __name__ == "__main__":
    main()
