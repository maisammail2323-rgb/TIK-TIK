import flet as ft

def main(page: ft.Page):
    page.title = "TikTik"
    page.bgcolor = "#000000"

    page.add(
        ft.Text("TikTik", size=32),
        ft.Text("Your short video app", size=18),
    )

if __name__ == "__main__":
    ft.run(main)