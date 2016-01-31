#!/usr/bin/env python

import os, re, sys, time, subprocess

try:
	import apt, aptsources.distro, aptsources.sourceslist
	apt_system = True
except ImportError:
	apt_system = False

try:
	import json
except ImportError:
	import simplejson as json


# Changing this to True disables this script, preventing video driver detection in Steam
disable_helper = False

class PackageInfo(object):
	def __init__(self):
		self.cache_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'driverhelper.cache')
		self.index_file = '/var/cache/apt/pkgcache.bin'
		self.sources_file = '/etc/apt/sources.list'
		self.sources_dir = '/etc/apt/sources.list.d'
		self.stale_timeout = 60*60*24*7

	@staticmethod
	def checkSystem():
		if not os.path.exists('/usr/bin/jockey-text'):
			return False
		if not os.path.exists('/sbin/modprobe'):
			return False
		return True

	def _isIntel(self, glinfo):
		# Don't use Vendor string for Intel, as it has changed recently from
		# "Tungsten Graphics, Inc." to "Intel Open Source Technology Center".
		# Intel recommends looking in GL_RENDERER string for 'Intel(R)'
		return glinfo[2].find('Intel(R)') != -1

	def _getCompatibleModuleNames(self, glinfo):
		# Intel doesn't use jockey
		if self._isIntel(glinfo):
			return []

		# Use jockey-text to find out what driver packages are compatible with installed hardware.
		module_names = []
		if not os.path.exists('/usr/bin/jockey-text'):
			return module_names
		p = subprocess.Popen(['/usr/bin/jockey-text', '--list'], stdout=subprocess.PIPE)
		output = p.communicate()[0]
		if p.returncode == 0 and output:
			for line in output.split('\n'):
				# Some video drivers are misconfigured as kernel modules, so special case these checks
				if line.startswith('xorg:') or line.startswith('kmod:nvidia') or line.startswith('kmod:fglrx'):
					m = re.search('^(xorg|kmod):(?P<module_name>\S+).*$', line)
					if m:
						module_names.append(m.groupdict()['module_name'])
		return module_names

	def _getPackageNameFromModuleName(self, module_name):
		# Rename _ to - to map back to package names. Jockey makes the reverse assumption.
		# NOTE: Could also look for driver names in Modalias fields for each package
		return module_name.replace('_', '-')

	def _findActiveModuleName(self, module_names):
		# Find which of these modules is actively in use
		if not module_names:
			return None
		elif module_names[0].find('nvidia') != -1:
			alias_name = 'nvidia'
		elif module_names[0].find('fglrx') != -1:
			alias_name = 'fglrx'
		else:
			return None
		p = subprocess.Popen(['/sbin/modprobe', '--resolve-alias', alias_name], stdout=subprocess.PIPE)
		return p.communicate()[0].strip()
	
	def _getNvidiaOrAMDPackageRecommendation(self, glinfo, module_names):
		# Have no recommendation for intel, yet
		results = dict(action='nothing')
		if self._isIntel(glinfo):
			return results

		# AMD and nVidia proprietary drivers require restricted components.
		if not self.areRestrictedComponentsEnabled():
			results['action'] = 'enable_restricted_components'
			results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=5101-QUPL-6040'
			return results

		# See if repository package index is stale, if so then update
		if self.isPackageIndexStale():
			results['action'] = 'update_package_index'
			results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=6796-TYZM-1345'
			return results

		# Find the module name in use.
		active_module_name = self._findActiveModuleName(module_names)
		
		# Find the candidate with the higest version
		# According to Canonical, it is ok to compare version strings of
		# compatible proprietary driver packages with each other.
		candidates = []
		cache = apt.Cache()
		installed = None
		for module_name in module_names:
			try:
				p = cache[self._getPackageNameFromModuleName(module_name)]
				if p.candidate:
					candidates.append((p, p.candidate))
				if p.installed and module_name == active_module_name:
					installed = (p, p.installed)
			except:
				pass
		candidates.sort(key=lambda t:t[1], reverse=True)

		# If no candidates, nothing to do
		if not candidates:
			results['action'] = 'no_candidates'
			return results

		# Prepare results
		def prep(t): 
			return dict(name=t[0].name, version=t[1].version)
		if candidates:
			results['candidate_package'] = prep(candidates[0])
		if installed:
			results['installed_package'] = prep(installed)

		# Figure out what to do
		if not installed:
			# No package-managed proprietary driver installed. Install candidate.
			if candidates:
				results['action'] = 'install_candidate'
				results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=8509-RFXM-1964'
		elif candidates and candidates[0][1] > installed[1]:
			# The candidate is a higher version. Is it the same package name?
			if candidates[0][0].name == installed[0].name:
				# Just need to update current installed package
				results['action'] = 'upgrade_installed_package'
				results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=5523-WTDV-5274'
			else:
				# Switch from one proprietary driver package to another
				results['action'] = 'switch_to_candidate'
				results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=1609-EIPG-1853'

		return results

	def isSubscribedXUpdatesPPA(self):
		try:
			sourceslist = aptsources.sourceslist.SourcesList()
			for e in sourceslist:
				if e.__dict__['disabled']:
					continue
				if e.__dict__['type'] != 'deb':
					continue
				if 'uri' not in e.__dict__:
					continue
				if e.__dict__['uri'].find('/x-updates/') != -1:
					return True
		except:
			pass
		return False

	def _getIntelPackageRecommendation(self, glinfo):
		# Only give recommendation for Intel
		results = dict(action='nothing')
		if not self._isIntel(glinfo):
			return results

		# Subscribed to x-updates PPA? If not, have the user do that.
		if not self.isSubscribedXUpdatesPPA():
			# Not found; ask the user to install this
			results['action'] = 'add_repository'
			results['repository_name'] = 'ppa:ubuntu-x-swat/x-updates'
			results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=5452-IOSM-1474'
			return results

		# x-updates installed. See if repository package index is stale
		if self.isPackageIndexStale():
			results['action'] = 'update_package_index'
			results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=6796-TYZM-1345'
			return results

		# Check to see if a newer candidate for libgl1-mesa-dri is available
		candidates = []
		try:
			p = apt.Cache()['libgl1-mesa-dri']
		except:
			return dict(action='no-candidates')

		if p.candidate and p.installed and p.candidate > p.installed:
			# Just need to update current installed package
			results['action'] = 'upgrade_installed_package'
			results['installed_package'] = dict(name=p.name, version=p.installed.version)
			results['candidate_package'] = dict(name=p.name, version=p.candidate.version)
			results['help_url'] = 'https://support.steampowered.com/kb_article.php?ref=5523-WTDV-5274'

		return results

	def _getHardwareVendor(self, glinfo, module_names):
		if self._isIntel(glinfo):
			return 'intel'
		if not module_names:
			return 'unknown'
		if module_names[0].find('nvidia') != -1:
			return 'nvidia'
		if module_names[0].find('fglrx') != -1:
			return 'amd'
		return 'unknown'

	def isPackageIndexStale(self):
		if not os.path.exists(self.index_file):
			return False
		if not os.path.exists(self.sources_file):
			return False

		# Get the more recent of sources.list and sources.list.d
		sources_mtime = os.stat(self.sources_file).st_mtime
		if os.path.exists(self.sources_dir):
			sources_dir_mtime = os.stat(self.sources_dir).st_mtime
			if sources_dir_mtime > sources_mtime:
				sources_mtime = sources_dir_mtime
			
		# See if sources.list has been changed without apt-get update being run
		index_stat = os.stat(self.index_file)
		if index_stat.st_mtime < sources_mtime:
			return True

		# See if it's stale based on this timeout
		if (time.time() - self.stale_timeout) > index_stat.st_mtime:
			return True
		return False

	def areRestrictedComponentsEnabled(self):
		# Is the restricted driver apt component enabled?
		distro = aptsources.distro.get_distro()
		sourceslist = aptsources.sourceslist.SourcesList()
		try:
			distro.get_sources(sourceslist)
		except:
			return True
		return 'restricted' in distro.enabled_comps

	def init(self, glinfo):
		# See if the script can run on this system.
		disabled = False
		if disable_helper or not apt_system:
			disabled = True
		if not PackageActions.checkSystem() or not PackageInfo.checkSystem():
			disabled = True

		# Figure out user recommendation
		result = {}
		if disabled:
			result['status'] = 'disabled'
		else:
			# The script can run on this system. Get the driver module names for installed hardware
			module_names = self._getCompatibleModuleNames(glinfo)

			# Get hardware vendor.
			result['hardware_vendor'] = self._getHardwareVendor(glinfo, module_names)
			result['index_stale'] = self.isPackageIndexStale()

			if self._isIntel(glinfo):
				# Intel doesn't use jockey. For Intel, only recommend the user
				# subscribe to x-updates, if they aren't already.
				result['recommendation'] = self._getIntelPackageRecommendation(glinfo)
			else:
				# The hardware is either Nvidia or AMD. Get a recommendation based on
				# the list of compatible driver packages.
				result['recommendation'] = self._getNvidiaOrAMDPackageRecommendation(glinfo, module_names)

			# Success
			result['status'] = 'success'

		# Save the result, it'll be queried by Steam later
		f = open(self.cache_file, 'w')
		if f:
			f.write(json.dumps(result))
			f.close()

	def getInfo(self):
		try:
			return json.loads(open(self.cache_file).read())
		except:
			return {}

class PackageActions(object):
	@staticmethod
	def checkSystem():
		if not os.path.exists('/usr/bin/jockey-gtk'):
			return False
		if not os.path.exists('/usr/bin/update-manager'):
			return False
		if not os.path.exists('/usr/bin/software-properties-gtk'):
			return False
		return True

	@staticmethod
	def enableRestrictedComponents(xid=0):
		# Let the user enable restricted components with convenient UI
		if os.path.exists('/usr/bin/software-properties-gtk'):
			p = subprocess.Popen(['/usr/bin/software-properties-gtk'])
			p.communicate()
			return 0
		return 1

	@staticmethod
	def upgradeInstalledPackage():
		# Just do a system upgrade
		if os.path.exists('/usr/bin/update-manager'):
			p = subprocess.Popen(['/usr/bin/update-manager'])
			p.communicate()
			return 0
		return 1

	@staticmethod
	def installCandidatePackage():	
		# Run jockey
		if os.path.exists('/usr/bin/jockey-gtk'):
			p = subprocess.Popen(['/usr/bin/jockey-gtk'])
			p.communicate()
			return 0
		return 1

	@staticmethod
	def switchToCandidatePackage():	
		# Run jockey
		if os.path.exists('/usr/bin/jockey-gtk'):
			p = subprocess.Popen(['/usr/bin/jockey-gtk'])
			p.communicate()
			return 0
		return 1

	@staticmethod
	def addRepository():
		# Open software-properties to the "Other Software" tab
		if os.path.exists('/usr/bin/software-properties-gtk'):
			p = subprocess.Popen(['/usr/bin/software-properties-gtk', '--open-tab', '1'])
			p.communicate()
			return 0
		return 1

	@staticmethod
	def updatePackageIndex():
		# Just do a system upgrade
		if os.path.exists('/usr/bin/update-manager'):
			p = subprocess.Popen(['/usr/bin/update-manager'])
			p.communicate()
			return 0
		return 1

def main(args):
	if len(args) == 0:
		return 1

	def signalSteam(action):
		# Don't depend on xdg-open or webbrowser module
		steamsh = os.path.join(os.path.expanduser('~/.steam/root'), 'steam.sh')
		cmd = '%s %s' % (steamsh, 'steam://open/%s' % action)
		os.system(cmd)

	pkgInfo = PackageInfo()
	if args[0] == 'begin_get_info':
		# Steam will not wait for this to complete
		# Args 1,2,3 are GL_VENDOR, GL_VERSION, GL_RENDERER strings
		if len(args) != 4:
			return 1
		pkgInfo.init((args[1], args[2], args[3]))
		signalSteam('driverhelperready')
		return 0

	if args[0] == 'get_info':
		# Steam waits synchronously for these results
		print(json.dumps(pkgInfo.getInfo()))
		return 0

	if args[0] == 'enable_restricted_components':
		if pkgInfo.areRestrictedComponentsEnabled():
			signalSteam('driverhelperrefresh')
			return 0
		if PackageActions.enableRestrictedComponents() != 0:
			return 1
		if pkgInfo.areRestrictedComponentsEnabled():
			signalSteam('driverhelperrefresh')
			return 0
		return 1

	if args[0] == 'upgrade_installed_package':
		# Steam will not wait for this to complete
		# args[1] has the package name
		return PackageActions.upgradeInstalledPackage()

	if args[0] == 'install_candidate_package':
		# Steam will not wait for this to complete
		# args[1] has the package name
		return PackageActions.installCandidatePackage()

	if args[0] == 'switch_to_candidate_package':
		# Steam will not wait for this to complete
		# args[1] has the package name
		return PackageActions.switchToCandidatePackage()

	if args[0] == 'add_repository':
		# Steam will not wait for this to complete
		# args[1] has the repository name
		if pkgInfo.isSubscribedXUpdatesPPA():
			signalSteam('driverhelperrefresh')
			return 0
		if PackageActions.addRepository() != 0:
			return 1
		if pkgInfo.isSubscribedXUpdatesPPA():
			signalSteam('driverhelperrefresh')
			return 0
		return 1

	if args[0] == 'update_package_index':
		# Steam will not wait for this to complete
		if not pkgInfo.isPackageIndexStale():
			signalSteam('driverhelperrefresh')
			return 0
		if PackageActions.updatePackageIndex() != 0:
			return 1
		if not pkgInfo.isPackageIndexStale():
			signalSteam('driverhelperrefresh')
			return 0
		return 1

	return 1

if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
