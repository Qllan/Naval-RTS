"""Девятка — pygame-прототип. Запуск: python main.py"""

import argparse

from nine.game import Game


def main():
    parser = argparse.ArgumentParser(description="Девятка — прототип морского симулятора")
    parser.add_argument("--seed", type=int, default=9, help="сид генерации мира")
    args = parser.parse_args()
    Game(seed=args.seed).run()


if __name__ == "__main__":
    main()
