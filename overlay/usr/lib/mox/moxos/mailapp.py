"""MOX Mail: write, seal and open post-quantum messages.

The mailbox itself (IMAP/SMTP accounts) opens in Geary. This window seals
messages and files so only your chosen contacts can read them.
"""
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk

from . import mail


def _text(view):
    buffer = view.get_buffer()
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)


def _area(placeholder=""):
    view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10, bottom_margin=10, left_margin=12, right_margin=12,
                        css_classes=["card"])
    view.get_buffer().set_text(placeholder)
    return view, Gtk.ScrolledWindow(child=view, vexpand=True, min_content_height=180)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MOX Mail", default_width=860, default_height=640)
        self.toast = Adw.ToastOverlay()
        stack = Adw.ViewStack()
        stack.add_titled_with_icon(self.write_page(), "write", "Write", "mail-message-new-symbolic")
        stack.add_titled_with_icon(self.open_page(), "open", "Open", "mail-read-symbolic")
        stack.add_titled_with_icon(self.contacts_page(), "contacts", "Contacts", "system-users-symbolic")
        header = Adw.HeaderBar(title_widget=Adw.ViewSwitcher(stack=stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        inbox = Gtk.Button(label="Mailbox", tooltip_text="Your email accounts (Geary)")
        inbox.connect("clicked", lambda _b: self.launch(["geary"]))
        header.pack_start(inbox)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.banner = Adw.Banner(revealed=False)
        self.banner.connect("button-clicked", self.create_key)
        body.append(self.banner)
        body.append(stack)
        stack.set_vexpand(True)
        view.set_content(body)
        self.toast.set_child(view)
        self.set_content(self.toast)
        self.refresh()

    # helpers ---------------------------------------------------------------
    def say(self, message):
        self.toast.add_toast(Adw.Toast(title=message, timeout=4))

    def copy(self, text):
        Gdk.Display.get_default().get_clipboard().set(text)

    def launch(self, cmd):
        try:
            subprocess.Popen(cmd)
        except OSError:
            self.say("Geary isn't installed. Run: sudo apt install geary")

    def refresh(self):
        if not mail.pq_ready():
            self.banner.set_title("Quantum Mail needs age 1.3. Run: sudo mox get quantum-mail")
            self.banner.set_button_label(None)
            self.banner.set_revealed(True)
        elif not mail.has_identity():
            self.banner.set_title("Create your post-quantum key to start")
            self.banner.set_button_label("Create key")
            self.banner.set_revealed(True)
        else:
            self.banner.set_revealed(False)
        names = Gtk.StringList()
        self.emails = sorted(mail.contacts())
        for email in self.emails:
            names.append(f"{mail.contacts()[email]['name']} <{email}>")
        self.to.set_model(names)
        self.fill_contacts()

    def create_key(self, _banner):
        try:
            mail.create_identity()
            self.say("Key created. Back up ~/.local/share/mox/mail/identity.txt")
        except mail.MailError as error:
            self.say(str(error))
        self.refresh()

    def page(self):
        return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14, margin_start=16, margin_end=16)

    # write -----------------------------------------------------------------
    def write_page(self):
        box = self.page()
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(label="To"))
        self.to = Gtk.DropDown(hexpand=True)
        row.append(self.to)
        box.append(row)
        self.message, scroll = _area()
        box.append(scroll)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        attach = Gtk.Button(label="Seal a file…")
        attach.connect("clicked", self.seal_file)
        seal = Gtk.Button(label="Seal and copy", css_classes=["suggested-action"])
        seal.connect("clicked", self.seal)
        buttons.append(attach)
        buttons.append(seal)
        box.append(buttons)
        box.append(Gtk.Label(label="Paste the sealed text into any email. Attach sealed files as they are.",
                             xalign=0, css_classes=["dim-label"]))
        return box

    def chosen(self):
        index = self.to.get_selected()
        if index == Gtk.INVALID_LIST_POSITION or index >= len(self.emails):
            raise mail.MailError("Add a contact first, from their key card.")
        return [self.emails[index]]

    def seal(self, _button):
        try:
            sealed = mail.seal(_text(self.message), self.chosen())
        except mail.MailError as error:
            self.say(str(error))
            return
        self.copy(sealed)
        self.message.get_buffer().set_text("")
        self.say("Sealed and copied. Paste it into your email.")

    def seal_file(self, _button):
        try:
            to = self.chosen()
        except mail.MailError as error:
            self.say(str(error))
            return
        dialog = Gtk.FileDialog(title="Choose a file to seal")

        def done(source, result):
            try:
                path = source.open_finish(result).get_path()
                self.say(f"Sealed to {mail.seal_file(path, to).name}")
            except mail.MailError as error:
                self.say(str(error))
            except Exception:
                pass
        dialog.open(self, None, done)

    # open ------------------------------------------------------------------
    def open_page(self):
        box = self.page()
        box.append(Gtk.Label(label="Paste a sealed email", xalign=0, css_classes=["heading"]))
        self.sealed, scroll = _area()
        box.append(scroll)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        open_file = Gtk.Button(label="Open a sealed file…")
        open_file.connect("clicked", self.open_file)
        read = Gtk.Button(label="Open", css_classes=["suggested-action"])
        read.connect("clicked", self.unseal)
        buttons.append(open_file)
        buttons.append(read)
        box.append(buttons)
        self.plain, scroll = _area()
        self.plain.set_editable(False)
        box.append(scroll)
        return box

    def unseal(self, _button):
        try:
            self.plain.get_buffer().set_text(mail.unseal(_text(self.sealed)))
        except mail.MailError as error:
            self.say(str(error))

    def open_file(self, _button):
        dialog = Gtk.FileDialog(title="Choose a .age file")

        def done(source, result):
            try:
                path = source.open_finish(result).get_path()
                out = mail.unseal_file(path)
                self.say(f"Opened to {out.name}")
                Gio.AppInfo.launch_default_for_uri(out.as_uri(), None)
            except mail.MailError as error:
                self.say(str(error))
            except Exception:
                pass
        dialog.open(self, None, done)

    # contacts --------------------------------------------------------------
    def contacts_page(self):
        box = self.page()
        mine = Gtk.Box(spacing=8)
        self.my_email = Gtk.Entry(hexpand=True, placeholder_text="Your email address")
        share = Gtk.Button(label="Copy my key card")
        share.connect("clicked", self.share)
        mine.append(self.my_email)
        mine.append(share)
        box.append(mine)
        box.append(Gtk.Label(label="Send your key card to people so they can seal mail to you. It's safe to share.",
                             xalign=0, css_classes=["dim-label"]))
        self.card, scroll = _area()
        scroll.set_min_content_height(110)
        box.append(Gtk.Label(label="Paste someone's key card", xalign=0, css_classes=["heading"]))
        box.append(scroll)
        add = Gtk.Button(label="Add contact", halign=Gtk.Align.END, css_classes=["suggested-action"])
        add.connect("clicked", self.add_contact)
        box.append(add)
        self.people = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        box.append(Gtk.ScrolledWindow(child=self.people, vexpand=True))
        return box

    def fill_contacts(self):
        while (child := self.people.get_first_child()) is not None:
            self.people.remove(child)
        for email, info in sorted(mail.contacts().items()):
            row = Adw.ActionRow(title=info["name"], subtitle=email)
            remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
            remove.connect("clicked", lambda _b, e=email: (mail.remove_contact(e), self.refresh()))
            row.add_suffix(remove)
            self.people.append(row)

    def share(self, _button):
        try:
            self.copy(mail.card(self.my_email.get_text().strip()))
            self.say("Key card copied")
        except mail.MailError as error:
            self.say(str(error))

    def add_contact(self, _button):
        try:
            contact = mail.read_card(_text(self.card))
        except mail.MailError as error:
            self.say(str(error))
            return
        self.card.get_buffer().set_text("")
        self.say(f"Added {contact['name']}")
        self.refresh()


def main():
    app = Adw.Application(application_id="org.mox.Mail")
    app.connect("activate", lambda a: Window(a).present())
    return app.run(sys.argv[:1])
