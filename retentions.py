import argparse


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # TODO - Define parser
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    print(arguments)


if __name__ == "__main__":
    main()
