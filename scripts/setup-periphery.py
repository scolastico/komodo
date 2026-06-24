import argparse
import sys
import os
import shutil
import platform
import urllib.request

def parse_args():
	p = argparse.ArgumentParser(
		prog="setup-periphery",
		description="Install systemd-managed Komodo Periphery",
		formatter_class=argparse.ArgumentDefaultsHelpFormatter,
	)

	p.add_argument(
		"--version", "-v",
		default=None,
		help="Override the image tag, e.g. 'unstable-release' or 'v2.0.0'. "
		     "Replaces the tag in --image when given."
	)

	p.add_argument(
		"--user", "-u",
		action="store_true",
		help="Install systemd '--user' service"
	)

	p.add_argument(
		"--root-directory", "-r",
		default="/etc/komodo",
		help="Specify a specific Periphery root directory."
	)

	p.add_argument(
		"--core-address", "-c",
		help="Specify the Komodo Core address for outbound connection. Leave blank to enable inbound connection server."
	)

	p.add_argument(
		"--connect-as", "-n",
		default=os.uname().nodename,
		help="Specify the Server name to connect as. Defaults to hostname."
	)

	p.add_argument(
		"--onboarding-key", "-k",
		help="Give an onboarding key for automatic Server onboarding into Komodo Core."
	)

	p.add_argument(
		"--force-service-file",
		help="Recreate the systemd service file even if it already exists."
	)

	p.add_argument(
		"--config-url",
		default="https://raw.githubusercontent.com/moghtech/komodo/refs/heads/main/config/periphery.config.toml",
		help="Use a custom config url."
	)

	p.add_argument(
		"--image",
		default="ghcr.io/scolastico/komodo-periphery:unstable-release",
		help="Docker image to extract the Periphery binary from."
	)

	p.add_argument(
		"--image-bin-path",
		default="/usr/local/bin/periphery",
		help="Path of the periphery binary inside the image."
	)

	args = p.parse_args()

	# If --version is given, swap out the tag of --image with it.
	if args.version != None:
		args.image = apply_image_tag(args.image, args.version)

	return args

def apply_image_tag(image, tag):
	# Replace the tag on an image reference without mistaking a registry port
	# (e.g. "host:5000/repo") for a tag.
	last_segment = image.rsplit("/", 1)[-1]
	if ":" in last_segment:
		image = image.rsplit(":", 1)[0]
	return f'{image}:{tag}'

def load_paths(args):
	home_dir = os.environ['HOME']
	if args.user:
		return [
			# home_dir
			home_dir,
			# binary location
			f'{home_dir}/.local/bin',
			# config location
	 		f'{home_dir}/.config/komodo',
			# service file location
	 		f'{home_dir}/.config/systemd/user',
		]
	else:
		return [
			# home_dir
			home_dir,
			# binary location
			"/usr/local/bin",
			# config location
	 		"/etc/komodo",
			# service file location
	 		"/etc/systemd/system",
		]

def has_docker():
	# Make sure the docker CLI is available before trying to extract from an image.
	return shutil.which("docker") is not None

def download_binary(args, bin_dir):
	if not has_docker():
		raise RuntimeError(
			"The 'docker' command was not found. Docker is required to extract "
			"the Periphery binary from an image. Install Docker and try again."
		)

	# stop periphery in case its currently in use
	user = ""
	if args.user:
		user = " --user"
	os.popen(f'systemctl{user} stop periphery')

	# ensure bin_dir exists
	if not os.path.isdir(bin_dir):
		os.makedirs(bin_dir)

	# delete binary if it already exists
	bin_path = f'{bin_dir}/periphery'
	if os.path.isfile(bin_path):
		os.remove(bin_path)

	# The image is published as a multi-arch manifest, so 'docker pull' picks
	# the matching binary for the host automatically (no per-arch name needed).
	arch = platform.machine().lower()
	print(f'detected architecture: {arch}')

	# pull the image
	print(f'pulling image {args.image}')
	if os.system(f'docker pull {args.image}') != 0:
		raise RuntimeError(
			f"Failed to pull image '{args.image}'.\n\n"
			f"Is Docker running and is the image reference valid?\n"
			f"You can override it with '--image' (and '--version' to set the tag)."
		)

	# Create a temporary (non-running) container so the binary can be copied out.
	container = "komodo-periphery-extract"
	# clean up any leftover container from a previous/interrupted run
	os.system(f'docker rm -f {container} > /dev/null 2>&1')

	if os.system(f'docker create --name {container} {args.image} > /dev/null') != 0:
		raise RuntimeError(f"Failed to create container from '{args.image}'")

	try:
		# copy the compiled binary out of the image to bin_path
		if os.system(f'docker cp {container}:{args.image_bin_path} {bin_path}') != 0:
			raise RuntimeError(
				f"Failed to copy '{args.image_bin_path}' out of the image.\n"
				f"If the binary lives elsewhere in the image, set '--image-bin-path'."
			)
	finally:
		# always remove the temporary container
		os.system(f'docker rm -f {container} > /dev/null 2>&1')

	# add executable permissions
	os.chmod(bin_path, 0o755)

def map_config_line(args, home_dir, line):
	## Handle root directory
	if line.startswith("root_directory ="):
		if args.root_directory != None:
			return f'root_directory = "{args.root_directory}"'
		if args.user:
			return f'root_directory = "{home_dir}/komodo"'
	## Handle core_address
	if line.startswith("# core_address =") and args.core_address != None:
		return f'core_address = "{args.core_address}"'
	## Handle connect_as
	if line.startswith("# connect_as ="):
		return f'connect_as = "{args.connect_as}"'
	## Handle onboarding key
	if line.startswith("# onboarding_key =") and args.onboarding_key != None:
		return f'onboarding_key = "{args.onboarding_key}"'
	return line

def write_config(args, home_dir, config_dir):
	config_file = f'{config_dir}/periphery.config.toml'

	# early return if config file already exists
	if os.path.isfile(config_file):
		print(f'Config at {config_file} already exists, skipping...')
		return

	print(f'creating config at {config_file}')

	# ensure config dir exists
	if not os.path.isdir(config_dir):
		os.makedirs(config_dir)

	template = urllib.request.urlopen(args.config_url).read().decode("utf-8").split("\n")
	lines = [map_config_line(args, home_dir, line) for line in template]
	config = "\n".join(lines)

	with open(config_file, "w", encoding="utf-8", newline="\n") as f:
		f.write(config)

def write_service_file(args, home_dir, bin_dir, config_dir, service_dir):
	service_file = f'{service_dir}/periphery.service'

	if args.force_service_file:
		print("forcing service file recreation")

	# early return is service file already exists
	if os.path.isfile(service_file):
		if args.force_service_file:
			print("deleting existing service file")
			os.remove(service_file)
		else:
			print(f'service file already exists at {service_file}, skipping...')
			return
	
	print(f'creating service file at {service_file}')
	
	# ensure service_dir exists
	if not os.path.isdir(service_dir):
		os.makedirs(service_dir)

	f = open(service_file, "x")
	f.write((
		"[Unit]\n"
		"Description=Agent to connect with Komodo Core\n"
		"\n"
		"[Service]\n"
		f'Environment="HOME={home_dir}"\n'
		f'ExecStart=/bin/sh -lc "{bin_dir}/periphery --config-path {config_dir}/periphery.config.toml"\n'
		"Restart=on-failure\n"
		"TimeoutStartSec=0\n"
		"\n"
		"[Install]\n"
		"WantedBy=default.target"
	))

	user = ""
	if args.user:
		user = " --user"
	os.popen(f'systemctl{user} daemon-reload')

def uses_systemd():
	# First check if systemctl is an available command, then check if systemd is the init system
	return shutil.which("systemctl") is not None and os.path.exists("/run/systemd/system/")

def main():
	args = parse_args()

	print("=====================")
	print(" PERIPHERY INSTALLER ")
	print("=====================")

	if not uses_systemd():
		print("This installer requires systemd and systemd wasn't found. Exiting")
		sys.exit(1)

	[home_dir, bin_dir, config_dir, service_dir] = load_paths(args)
	
	print(f'image: {args.image}')
	print(f'core address: {args.core_address}')
	print(f'connect as: {args.connect_as}')
	print(f'user install: {args.user}')
	print(f'home dir: {home_dir}')
	print(f'bin dir: {bin_dir}')
	print(f'config dir: {config_dir}')
	print(f'service file dir: {service_dir}')

	download_binary(args, bin_dir)
	write_config(args, home_dir, config_dir)
	write_service_file(args, home_dir, bin_dir, config_dir, service_dir)

	user = ""
	if args.user:
		user = " --user"

	print("Starting Periphery...")
	print(os.popen(f'systemctl{user} start periphery').read())

	print("Finished Periphery setup.\n")
	print(f'Note. Use "systemctl{user} status periphery" to make sure Periphery is running')
	print(f'Note. Use "systemctl{user} enable periphery" to have Periphery start on system boot')
	if args.user:
		print(f'Note. Use "sudo loginctl enable-linger $USER" to make sure Periphery keeps runnning after user logs out')

main()
