import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

const MARGIN = 28;
const WIDTH = 300;

function card(title) {
    const box = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, style_class: 'mox-card', width: WIDTH});
    box.add_child(new St.Label({text: title, style_class: 'mox-title'}));
    return box;
}

function line(parent, style = 'mox-line') {
    const label = new St.Label({text: '', style_class: style});
    label.clutter_text.line_wrap = true;
    parent.add_child(label);
    return label;
}

export default class MoxWidgets extends Extension {
    enable() {
        this._box = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, style_class: 'mox-widgets'});

        const net = card('NETWORK');
        this._down = line(net, 'mox-big');
        this._up = line(net);
        this._speed = line(net, 'mox-dim');

        const threats = card('THREATS');
        this._blocked = line(threats, 'mox-big');
        this._botnets = line(threats);
        this._exploit = line(threats, 'mox-dim');

        this._setup = line(net, 'mox-dim');
        this._box.add_child(net);
        this._box.add_child(threats);
        Main.layoutManager._backgroundGroup.add_child(this._box);

        // Top bar button: brings the widgets above your windows, click again to put them back
        this._button = new PanelMenu.Button(0.0, 'MOX Widgets', true);
        this._button.add_child(new St.Icon({icon_name: 'view-grid-symbolic', style_class: 'system-status-icon'}));
        this._button.connect('button-press-event', () => {
            this._toggle();
            return Clutter.EVENT_STOP;
        });
        Main.panel.addToStatusArea('mox-widgets', this._button, 0, 'right');

        this._place();
        this._monitors = Main.layoutManager.connect('monitors-changed', () => this._place());
        this._refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _toggle() {
        const front = Main.layoutManager.uiGroup;
        const target = this._box.get_parent() === front ? Main.layoutManager._backgroundGroup : front;
        this._box.get_parent().remove_child(this._box);
        target.add_child(this._box);
        this._place();
    }

    _place() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (monitor)
            this._box.set_position(monitor.x + monitor.width - WIDTH - MARGIN, monitor.y + Main.panel.height + MARGIN);
    }

    _refresh() {
        const parent = this._box.get_parent();
        parent?.set_child_above_sibling(this._box, null);
        try {
            const [ready, status] = GLib.file_get_contents('/run/mox-setup');
            this._setup.text = ready ? `Setting up MOX: ${new TextDecoder().decode(status).trim()}` : '';
        } catch (error) {
            this._setup.text = '';
        }
        const path = GLib.build_filenamev([GLib.get_user_cache_dir(), 'mox', 'widgets.json']);
        try {
            const [ok, bytes] = GLib.file_get_contents(path);
            if (!ok)
                return;
            const data = JSON.parse(new TextDecoder().decode(bytes));
            this._down.text = `↓ ${data.down}`;
            this._up.text = `↑ ${data.up}`;
            this._speed.text = `Last test: ${data.speed}`;
            this._blocked.text = `${data.blocked} blocked today`;
            if (data.botnets !== null && data.botnets !== undefined)
                this._botnets.text = `${data.botnets} active botnet servers\nMost active: ${data.family || 'n/a'}`;
            else
                this._botnets.text = 'Threat feed offline';
            this._exploit.text = data.exploit ? `Latest exploited: ${data.exploit}` : '';
        } catch (error) {
            this._down.text = 'Starting…';
        }
    }

    disable() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = null;
        if (this._monitors)
            Main.layoutManager.disconnect(this._monitors);
        this._monitors = null;
        this._button?.destroy();
        this._button = null;
        this._box?.destroy();
        this._box = null;
    }
}
