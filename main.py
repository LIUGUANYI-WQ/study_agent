from dotenv import load_dotenv
from src.app import App


def main():
    load_dotenv()
    App().run()


if __name__ == "__main__":
    main()
