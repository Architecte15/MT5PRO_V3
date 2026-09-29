from app.main import main
import sys

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--mode", "demo", *sys.argv[1:]]
    main()
