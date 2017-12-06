# $language = "python"
# $interface = "1.0"

import os
import sys
import logging

# Add script directory to the PYTHONPATH so we can import our modules (only if run from SecureCRT)
if 'crt' in globals():
    script_dir, script_name = os.path.split(crt.ScriptFullName)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
else:
    script_dir, script_name = os.path.split(os.path.realpath(__file__))

# Now we can import our custom modules
from securecrt_tools import script_types
from securecrt_tools import utilities
# Import message box constants as names
from securecrt_tools.message_box_const import *

# Create global logger so we can write debug messages from any function (if debug mode setting is enabled in settings).
logger = logging.getLogger("securecrt")
logger.debug("Starting execution of {}".format(script_name))


# ################################################   SCRIPT LOGIC   ###################################################

def script_main(script):
    """
    | SINGLE device script
    | Author: Jamie Caesar
    | Email: jcaesar@presidio.com

    This script will grab the detailed CDP information from a Cisco IOS or NX-OS device and create SecureCRT sessions
    based on the information.  By default all sessions will be created as SSH2, so you may have
    to manually change some sessions to make them work, depending on the device capabilities/configuration.

    Script Settings (found in settings/settings.ini):
    folder - The path starting from the <SecureCRT Config>/Sessions/ directory where the sessions will be created.
    strip_domains -  A list of domain names that will be stripped away if found in the CDP remote device name.

    :param script: A subclass of the sessions.Session object that represents this particular script session (either
                    SecureCRTSession or DirectSession)
    :type script: script_types.Script
    """
    # Start session with device, i.e. modify term parameters for better interaction (assuming already connected)
    script.start_cisco_session()

    # Validate device is running a supported OS
    supported_os = ["IOS", "NXOS"]
    if script.os not in supported_os:
        logger.debug("Unsupported OS: {0}.  Raising exception.".format(script.os))
        raise script_types.UnsupportedOSError("Remote device running unsupported OS: {0}.".format(script.os))

    send_cmd = "show cdp neighbors detail"

    raw_cdp = script.get_command_output(send_cmd)

    template_file = script.get_template("cisco_os_show_cdp_neigh_det.template")

    cdp_table = utilities.textfsm_parse_to_list(raw_cdp, template_file)

    # Since "System Name" is a newer NXOS feature -- try to extract it from the device ID when its empty.
    strip_list = script.settings.getlist("create_sessions_from_cdp", "strip_domains")
    for entry in cdp_table:
        # entry[2] is system name, entry[1] is device ID
        if entry[2] == "":
            entry[2] = utilities.extract_system_name(entry[1], strip_list=strip_list)

    session_list = create_session_list(cdp_table)

    # Get the destination directory from settings
    dest_folder = script.settings.get("create_sessions_from_cdp", "folder")

    for device in session_list:
        system_name = device[0]
        mgmt_ip = device[1]
        script.create_new_saved_session(system_name, mgmt_ip, folder=dest_folder)
        # Track the names of the hosts we've made already
        logger.debug("Created session for {}.".format(system_name))

    # Calculate statistics
    num_created = len(session_list)
    num_skipped = len(cdp_table) - len(session_list)

    setting_msg = "{} sessions created in the Sessions sub-directory '{}'\n" \
                  "\n" \
                  "{} sessions skipped (no IP or duplicate)".format(num_created, dest_folder, num_skipped)
    script.message_box(setting_msg, "Sessions Created", ICON_INFO)

    # Return terminal parameters back to the original state.
    script.end_cisco_session()


def create_session_list(cdp_list):
    """
    This function takes the TextFSM output of the CDP information and uses it to create a list of new SecureCRT sessions
    to create (system name and IP address).

    :param cdp_list: The TextFSM output after processing the "show cdp neighbor detail" output
    :type cdp_list: list

    :return: A list (system name and IP address) of the sessions that need to be created.
    :rtype: list
    """
    created = set()
    session_list = []
    for device in cdp_list:
        # Extract hostname and IP to create session
        system_name = device[2]

        # If we couldn't get a System name, use the device ID
        if system_name == "":
            system_name = device[1]

        if system_name in created:
            logger.debug("Skipping {} because it is a duplicate.".format(system_name))
            # Go directly to the next device (skip this one)
            continue

        mgmt_ip = device[7]
        if mgmt_ip == "":
            if device[4] == "":
                # If no mgmt IP or interface IP, skip device.
                logger.debug("Skipping {} because cannot find IP in CDP data.".format(system_name))
                # Go directly to the next device (skip this one)
                continue
            else:
                mgmt_ip = device[4]
                logger.debug("Using interface IP ({}) for {}.".format(mgmt_ip, system_name))
        else:
            logger.debug("Using management IP ({}) for {}.".format(mgmt_ip, system_name))

        # Add device to session_list
        session_list.append((system_name, mgmt_ip,))
        # Create a new session from the default information.
        created.add(system_name)

    return session_list


# ################################################  SCRIPT LAUNCH   ###################################################

# If this script is run from SecureCRT directly, use the SecureCRT specific class
if __name__ == "__builtin__":
    crt_script = script_types.CRTScript(crt)
    script_main(crt_script)

# If the script is being run directly, use the simulation class
elif __name__ == "__main__":
    direct_script = script_types.DirectScript(os.path.realpath(__file__))
    script_main(direct_script)