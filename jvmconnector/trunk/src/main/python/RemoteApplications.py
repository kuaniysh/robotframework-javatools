import glob
import os
import re
import tempfile
import time

from java.util.jar import JarFile
from java.util.zip import ZipException
from java.io import IOException

from robot.utils import normalize, NormalizedDict, timestr_to_secs
from robot.running import NAMESPACES
from robot.running.namespace import IMPORTER
from robot.libraries.BuiltIn import BuiltIn
from robot.libraries.OperatingSystem import OperatingSystem

from org.springframework.beans.factory import BeanCreationException
from org.springframework.remoting import RemoteAccessException
from org.springframework.remoting.rmi import RmiProxyFactoryBean

from org.robotframework.jvmconnector.client import RobotRemoteLibrary
from org.robotframework.jvmconnector.server import RmiInfoStorage, LibraryImporter


class InvalidURLException(Exception):
    pass


DATABASE = os.path.join(tempfile.gettempdir(), 'launcher.txt')

def get_arg_spec(method):
    """Returns info about args in a tuple (args, defaults, varargs)

    args     - tuple of all accepted arguments
    defaults - tuple of default values
    varargs  - name of the argument accepting varargs or None
    """
    # Code below is based on inspect module's getargs and getargspec 
    # methods. See their documentation and/or source for more details. 
    func = method.im_func
    first_arg = 1        # this drops 'self' from methods' args
    co = func.func_code
    nargs = co.co_argcount
    args = co.co_varnames[first_arg:nargs]
    defaults = func.func_defaults
    if defaults is None:
        defaults = ()
    if co.co_flags & 4:                      # 4 == CO_VARARGS
        varargs =  co.co_varnames[nargs]
    else:
        varargs = None
    return args, defaults, varargs


class RemoteLibrary:

    def __init__(self, uri):
        self._uri = uri
        self._open_connection()
        self._keywords = None

    def _open_connection(self):
        self._remote_lib = RobotRemoteLibrary(self._uri)

    def get_keyword_names(self):
        if self._keywords is None:
            self._keywords = list(self._remote_lib.getKeywordNames())
        return self._keywords

    def has_keyword(self, name):
        return name in self._keywords

    def run_keyword(self, name, args):
        #TODO: Add polling to RemoteLibrary to make it easier to see whether 
        #there is connection or not. If not,  reconnect.
        return self._remote_lib.runKeyword(name, args)


class RemoteApplication:
    ROBOT_LIBRARY_SCOPE = 'GLOBAL'

    def __init__(self):
        self._libs = []
        self._rmi_client = None
        self._alias = None

    def application_started(self, alias=None, timeout='60 seconds', rmi_url=None):
        if self._rmi_client:
            raise RuntimeError("Application already connected")
        self._alias = alias
        timeout = timestr_to_secs(timeout or '60 seconds')
        self._rmi_client = self._connect_to_base_rmi_service(alias, timeout, rmi_url)

    def _connect_to_base_rmi_service(self, alias, timeout, rmi_url): 
        start_time = time.time()
        while time.time() - start_time < timeout:
            url = self._retrieve_base_rmi_url(rmi_url)
            try:
                print "*TRACE* Trying to connect to rmi url '%s'" % url
                return self._create_rmi_client(url)
            except (BeanCreationException, RemoteAccessException,
                    InvalidURLException):
                time.sleep(2)
        self._could_not_connect(alias)

    def _retrieve_base_rmi_url(self, url):
        #TODO: Get from started apps DB
        return url or RmiInfoStorage(DATABASE).retrieve()

    def _create_rmi_client(self, url):
        if not re.match('rmi://[^:]+:\d{1,5}/.*', url):
            raise InvalidURLException()
        rmi_client = RmiProxyFactoryBean(serviceUrl=url,
                                         serviceInterface=LibraryImporter)
        rmi_client.prepare()
        rmi_client.afterPropertiesSet()
        self._save_base_url_and_clean_db(url)
        return rmi_client

    def _save_base_url_and_clean_db(self, url):
        self._rmi_url = url
        if os.path.exists(DATABASE):
            os.remove(DATABASE)

    def _could_not_connect(self, alias):
        alias = alias or ''
        raise RuntimeError("Could not connect to application %s" % alias)

    def take_libraries_into_use(self, *library_names):
        for name in library_names:
            self.take_library_into_use(name)

    def take_library_into_use(self, library_name):
        #TODO: Add support for arguments
        self._check_connection()
        library_url = self._import_remote_library(library_name)
        library = RemoteLibrary(library_url)
        self._libs.append(library)
        return library.get_keyword_names()

    def _check_connection(self):
        if self._rmi_client is None:
            raise RuntimeError("No connection established. Use keyword " +
                               "'Application Started' before this keyword.")

    def _import_remote_library(self, library_name): 
        try:
            return self._rmi_client.getObject().importLibrary(library_name)
        except (BeanCreationException, RemoteAccessException):
            self._could_not_connect(self._alias)

    def close_application(self):
        self._check_connection()
        try:
            self._rmi_client.getObject().closeService()
        except RemoteAccessException:
            self._rmi_client = None
            return
        raise RuntimeError('Could not close application.')

    def get_keyword_names(self):
        kws = []
        for lib in self._libs:
            kws.extend(lib.get_keyword_names())
        return kws

    def run_keyword(self, name, args):
        for lib in self._libs:
            if lib.has_keyword(name):
                return lib.run_keyword(name, args)


class RemoteApplicationsConnector:
    """Library for handling multiple remote applications.

    """
    #TODO: Add generic information about 
    #1) Starting Applications
    #2) Finding and taking Libraries into use
    #3) Starting Remote Applications

    _kws = ['start_application', 'application_started', 'switch_to_application',
            'close_all_applications', 'close_application', 
            'take_libraries_into_use','take_library_into_use']

    def __init__(self):
        self._initialize()

    def _initialize(self):
        self._apps = NormalizedDict()
        self._active_app = None

    def start_application(self, alias, command, timeout='60 seconds', 
                          lib_dir=None, port=None):
        """Starts the application, connects to it and makes it active application.

        `command` is the command used to start the application from the command
        line. It can be any command that finally starts JVM. TODO: Add examples.
        
        `libdir` is needed always when Java process is started with Java Web 
        Start or in case libraries are not in the CLASSPATH. It is path to the 
        directory containing jar files which are required for running the tests.
        In another words these jar files should contain libraries that you want
        to remotely take into use (packaged in jars). In case you are using 1.5
        Java, you should package all these libraries to the `jvm_connector_jar`.
        
        `port` is port where the SUT starts server which provides taking
        libraries into use and executing the keywords. *Note:* If the 
        application is used to start other applications, port should NOT be used.
        """
        self._alias_in_use(alias)
        os.environ['JAVA_TOOL_OPTIONS'] =  self._get_java_agent(lib_dir, port)
        OperatingSystem().start_process(command)
        os.environ['JAVA_TOOL_OPTIONS'] = ''
        rmi_url = port and 'rmi://localhost:%s/robotrmiservice' % port or None
        self.application_started(alias, timeout, rmi_url)

    def _alias_in_use(self, alias):
        if self._apps.has_key(alias):
            raise RuntimeError("Application with alias '%s' already in use" % alias)

    def _get_java_agent(self, lib_dir, port):
        jars = glob.glob('%s%s*.jar' % (lib_dir, os.path.sep))
        print "*TRACE* found following library jars: %s" % (jars)
        jvm_connector_jar = self._get_jvm_connector_jar()
        port = port and ['PORT=%s' % port] or []
        return '-javaagent:%s=%s' % (jvm_connector_jar, 
                                     os.path.pathsep.join(port + jars))

    def _get_jvm_connector_jar(self):
        for jar_file in self._get_jars_from_classpath():
            try:
                premain_class = JarFile(jar_file).getManifest().getMainAttributes().getValue('Premain-Class')
            except ZipException, IOExcetion:
                continue
            if premain_class == 'org.robotframework.jvmconnector.agent.RmiServiceAgent':
                print "*TRACE* Found jvm_connector jar '%s'" % jar_file
                return jar_file
        raise RuntimeError("Could not find jvmconnector jarfile from CLASSPATH")

    def _get_jars_from_classpath(self):
        jars = []
        if os.environ.has_key('CLASSPATH'):
            jars = jars + os.environ['CLASSPATH'].split(os.path.pathsep)
        if os.environ.has_key('classpath'):
            jars = jars + os.environ['classpath'].split(os.path.pathsep)
        return jars

    def application_started(self, alias, timeout='60 seconds', rmi_url=None):
        """Connects to started application and switches to it.

        `alias` is the alias name for the application. When using multiple 
        applications alias is used to switch between them with keyword `Switch 
        To Application`.
        
        `timeout` is the time to wait the application to be started to the point
        where the testing capabilities are initialized and the connection between
        RemoteApplications and SUT can be established.
        
        `rmi_url` is url that can be used to connect to the SUT. When used
        locally there is usually no need to give the `rmi_url`. However, when
        the SUT is running on other machine, the normal mechanism used to find
        the SUT is not enough and you need to provide the `rmi_url`. In case
        port is not configured on remote side, you can find the `rmi_url` after
        started the SUT using the javaagent explained in `Introduction`.
        
        """
        self._alias_in_use(alias)
        app = RemoteApplication()
        app.application_started(alias, timeout, rmi_url)
        self._apps[alias] = app
        self._active_app = app

    def switch_to_application(self, alias):
        """Changes the application where the keywords are executed.
        
        `alias` is the name of the application and it have been given with the
        `Application Started` keyword."""
        self._check_application_in_use(alias)
        self._active_app = self._apps[alias]

    def _check_application_in_use(self, alias):
        if not self._apps.has_key(alias):
            raise RuntimeError("No Application with alias '%s' in use" % alias)

    def take_libraries_into_use(self, *library_names):
        """Takes the libraries into use at the remote application.
        
        `library_names` contains all the libraries that you want to take into
        use on the remote side. *Note:* See 'Start Application' for information
        how to provide library jar files."""
        self._check_active_app()
        self._active_app.take_libraries_into_use(*library_names)
        self._update_keywords_to_robot()

    def _check_active_app(self):
        if self._active_app is None:
            raise RuntimeError("No application selected")

    def _update_keywords_to_robot(self):
        # TODO: When Robot has better support for reimporting libraries,
        # update following code to use that approach. See RF issue 293.
        lib_name = os.path.splitext(os.path.basename(__file__))[0]
        self._remove_lib_from_current_namespace(lib_name)
        self._remove_lib_from_importer(lib_name, [])
        BuiltIn().import_library(lib_name)

    def _remove_lib_from_current_namespace(self, name):
        testlibs = NAMESPACES.current._testlibs
        if testlibs.has_key(name):
            del(testlibs[name])

    def _remove_lib_from_importer(self, name, args):
        if IMPORTER._libraries.has_key((name, tuple(args))):
            del(IMPORTER._libraries[(name, tuple(args))])
        elif IMPORTER._libraries.has_key((name, args)):
                index = IMPORTER._libraries._keys.index((name, args))
                IMPORTER._libraries._keys.pop(index)
                IMPORTER._libraries._libs.pop(index)

    def take_library_into_use(self, library_name):
        """Takes given library into use.
        
        See `Take Libraries Into Use` keyword for more details.
        """
        self._check_active_app()
        self._active_app.take_library_into_use(library_name)
        self._update_keywords_to_robot()

    def close_all_applications(self):
        """Closes all the applications"""
        for alias in self._apps.keys():
            try:
                self._apps[alias].close_application()
            except RuntimeError:
                print "*WARN* Could not close application '%s'" % (alias)
        self._initialize()

    def close_application(self, alias=None):
        """Closes application.
        
        If `alias` is given, closes application related to the alias. 
        Otherwise closes the active application."""
        alias = alias or self._get_active_app_alias()
        print "*TRACE* Closing application '%s'" % alias
        self._check_application_in_use(alias)
        if self._apps[alias] == self._active_app:
            self._active_app = None
        try:
            self._apps[alias].close_application()
            print "Closed application '%s'" % (alias)
        finally:
            del(self._apps[normalize(alias)])

    def _get_active_app_alias(self):
        self._check_active_app()
        for alias, app in self._apps.items():
            if app == self._active_app:
                return alias

    def get_keyword_names(self):
        #FIXME: Handle dublicate kw names
        kws = []
        for app in self._apps.values():
            kws.extend(app.get_keyword_names())
        return kws + self._kws

    def run_keyword(self, name, args):
        method = self._get_method(name)
        if method:
            return method(*args)
        return self._active_app.run_keyword(name, args)

    def _get_method(self, name):
        if name in self._kws:
            return getattr(self, name)
        return None

    def get_keyword_arguments(self, name):
        method = self._get_method(name)
        if method:
            args, defaults, varargs = get_arg_spec(method)
            arguments = list(args[:len(args)-len(defaults)])
            defaults = [ '%s=%s' % (arg, default) for arg, default in zip(list(args[len(arguments):]), list(defaults)) ]
            varargs = varargs and ['*%s' % varargs] or []
            return arguments + defaults + varargs
        return ['*args']

    def get_keyword_documentation(self, name):
        method = self._get_method(name)
        if method:
            return method.__doc__
        return ''


class RemoteApplications:
    ROBOT_LIBRARY_SCOPE = 'GLOBAL'
    _connector = RemoteApplicationsConnector()
    __doc__ = _connector.__doc__

    def get_keyword_names(self):
        names = self._connector.get_keyword_names()
        return names

    def run_keyword(self, name, args):
        return self._connector.run_keyword(name, args)

    def get_keyword_arguments(self, name):
        return self._connector.get_keyword_arguments(name)

    def get_keyword_documentation(self, name):
        return self._connector.get_keyword_documentation(name)
