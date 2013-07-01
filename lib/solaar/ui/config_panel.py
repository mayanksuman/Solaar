#
#
#

from __future__ import absolute_import, division, print_function, unicode_literals

from gi.repository import Gtk, GLib

from logitech.unifying_receiver.settings import KIND as _SETTING_KIND

#
# a separate thread is used to read/write from the device
# so as not to block the main (GUI) thread
#

try:
	from Queue import Queue as _Queue
except ImportError:
	from queue import Queue as _Queue
_apply_queue = _Queue(8)

def _process_apply_queue():
	def _write_start(sbox):
		_, failed, spinner, control = sbox.get_children()
		control.set_sensitive(False)
		failed.set_visible(False)
		spinner.set_visible(True)
		spinner.start()

	while True:
		task = _apply_queue.get()
		assert isinstance(task, tuple)
		device_is_online = True
		# print ("task", *task)
		if task[0] == 'write':
			_, setting, value, sbox = task
			GLib.idle_add(_write_start, sbox, priority=0)
			value = setting.write(value)
		elif task[0] == 'read':
			_, setting, force_read, sbox, device_is_online = task
			value = setting.read(not force_read)
		GLib.idle_add(_update_setting_item, sbox, value, device_is_online, priority=99)

from threading import Thread as _Thread
_queue_processor = _Thread(name='SettingsProcessor', target=_process_apply_queue)
_queue_processor.daemon = True
_queue_processor.start()

#
#
#

def _create_toggle_control(setting):
	def _switch_notify(switch, _, s):
		if switch.get_sensitive():
			_apply_queue.put(('write', s, switch.get_active() == True, switch.get_parent()))

	c = Gtk.Switch()
	c.connect('notify::active', _switch_notify, setting)
	return c

def _create_choice_control(setting):
	def _combo_notify(cbbox, s):
		if cbbox.get_sensitive():
			_apply_queue.put(('write', s, cbbox.get_active_id(), cbbox.get_parent()))

	c = Gtk.ComboBoxText()
	for entry in setting.choices:
		c.append(str(entry), str(entry))
	c.connect('changed', _combo_notify, setting)
	return c

# def _create_slider_control(setting):
# 	def _slider_notify(slider, s):
# 		if slider.get_sensitive():
# 			_apply_queue.put(('write', s, slider.get_value(), slider.get_parent()))
#
# 	c = Gtk.Scale(setting.choices)
# 	c.connect('value-changed', _slider_notify, setting)
#
# 	return c

#
#
#

def _create_sbox(s):
	sbox = Gtk.HBox(homogeneous=False, spacing=6)
	sbox.pack_start(Gtk.Label(s.label), False, False, 0)

	spinner = Gtk.Spinner()
	spinner.set_tooltip_text('Working...')

	failed = Gtk.Image.new_from_icon_name('dialog-warning', Gtk.IconSize.SMALL_TOOLBAR)
	failed.set_tooltip_text('Failed to read value from the device.')

	if s.kind == _SETTING_KIND.toggle:
		control = _create_toggle_control(s)
	elif s.kind == _SETTING_KIND.choice:
		control = _create_choice_control(s)
	# elif s.kind == _SETTING_KIND.range:
	# 	control = _create_slider_control(s)
	else:
		raise NotImplemented

	control.set_sensitive(False)  # the first read will enable it
	sbox.pack_end(control, False, False, 0)
	sbox.pack_end(spinner, False, False, 0)
	sbox.pack_end(failed, False, False, 0)

	if s.description:
		sbox.set_tooltip_text(s.description)

	sbox.show_all()
	spinner.start()  # the first read will stop it
	failed.set_visible(False)

	return sbox


def _update_setting_item(sbox, value, is_online=True):
	_, failed, spinner, control = sbox.get_children()
	spinner.set_visible(False)
	spinner.stop()

	# print ("update", control, "with new value", value)
	if value is None:
		control.set_sensitive(False)
		failed.set_visible(is_online)
		return

	failed.set_visible(False)
	if isinstance(control, Gtk.Switch):
		control.set_active(value)
	elif isinstance(control, Gtk.ComboBoxText):
		control.set_active_id(str(value))
	# elif isinstance(control, Gtk.Scale):
	# 	control.set_value(int(value))
	else:
		raise NotImplemented
	control.set_sensitive(True)

#
#
#

# config panel
_box = None
_items = {}

def create():
	global _box
	assert _box is None
	_box = Gtk.VBox(homogeneous=False, spacing=8)
	_box._last_device = None
	return _box


def update(device, is_online=None):
	assert _box is not None
	assert device
	device_id = (device.receiver.path, device.number)
	if is_online is None:
		is_online = bool(device.online)

	# if the device changed since last update, clear the box first
	if device_id != _box._last_device:
		_box.set_visible(False)
		_box._last_device = device_id

	# hide controls belonging to other devices
	for k, sbox in _items.items():
		sbox = _items[k]
		sbox.set_visible(k[0:2] == device_id)

	for s in device.settings:
		k = (device_id[0], device_id[1], s.name)
		if k in _items:
			sbox = _items[k]
		else:
			sbox = _items[k] = _create_sbox(s)
			_box.pack_start(sbox, False, False, 0)

		_apply_queue.put(('read', s, False, sbox, is_online))

	_box.set_visible(True)


def clean(device):
	"""Remove the controls for a given device serial.
	Needed after the device has been unpaired.
	"""
	assert _box is not None
	device_id = (device.receiver.path, device.number)
	for k in list(_items.keys()):
		if k[0:2] == device_id:
			_box.remove(_items[k])
			del _items[k]


def destroy():
	global _box
	_box = None
	_items.clear()