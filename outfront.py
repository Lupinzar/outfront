#nuitka-project: --standalone
#nuitka-project: --include-data-files={MAIN_DIRECTORY}/*.png=./
#nuitka-project: --plugin-enable=tk-inter
#nuitka-project: --windows-console=disable
#nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/icon.ico

from app import App

def main():
    app = App()
    app.title('outfront')
    app.mainloop()

if __name__ == "__main__":
    main()
