import xbmc
import xbmcgui
import xbmcaddon
import os

class SkipIntroDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.callback = kwargs.get('callback')
        super(SkipIntroDialog, self).__init__(*args)

    def onInit(self):
        xbmc.log('SkipIntro: Button window initialized', xbmc.LOGINFO)
        try:
            self.button = self.getControl(1)
            xbmc.log('SkipIntro: Got button control', xbmc.LOGINFO)
            self.setFocus(self.button)
            xbmc.log('SkipIntro: Button focused', xbmc.LOGINFO)
        except Exception as e:
            xbmc.log(f'SkipIntro: Error in onInit: {str(e)}', xbmc.LOGERROR)
            import traceback
            xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)

    def onClick(self, controlId):
        xbmc.log(f'SkipIntro: Button clicked - control ID: {controlId}', xbmc.LOGINFO)
        if controlId == 1:  # Skip button
            if self.callback:
                xbmc.log('SkipIntro: Executing skip callback', xbmc.LOGINFO)
                self.callback()
            self.close()

    def onAction(self, action):
        actionId = action.getId()
        xbmc.log(f'SkipIntro: Button received action - ID: {actionId}', xbmc.LOGINFO)
        if actionId in [xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK]:
            xbmc.log('SkipIntro: Button dismissed with back/escape', xbmc.LOGINFO)
            self.close()

class PlayerUI:
    def __init__(self):
        self.prompt_shown = False
        self._dialog = None

    def prompt_skip_intro(self, callback):
        """Show skip intro button and execute callback if user clicks it"""
        xbmc.log('SkipIntro: Showing skip intro button', xbmc.LOGINFO)
        try:
            if not self.prompt_shown and self._dialog is None:
                addon = xbmcaddon.Addon()
                addon_path = addon.getAddonInfo('path')
                xml_path = os.path.join(addon_path, 'resources', 'skins', 'default', '720p', 'skip_button.xml')
                
                xbmc.log(f'SkipIntro: XML path: {xml_path}', xbmc.LOGINFO)
                xbmc.log(f'SkipIntro: XML exists: {os.path.exists(xml_path)}', xbmc.LOGINFO)
                
                self._dialog = SkipIntroDialog(
                    'skip_button.xml',
                    addon_path,
                    'default',
                    '720p',
                    callback=callback
                )
                xbmc.log('SkipIntro: Dialog instance created', xbmc.LOGINFO)
                
                self._dialog.show()
                xbmc.log('SkipIntro: Dialog show() called', xbmc.LOGINFO)
                
                self.prompt_shown = True
                return True
            return False
                
        except Exception as e:
            xbmc.log(f'SkipIntro: Error showing skip button: {str(e)}', xbmc.LOGERROR)
            import traceback
            xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
            self.cleanup()
            return False
            
    def cleanup(self):
        """Clean up resources"""
        if self._dialog is not None:
            self._dialog.close()
            self._dialog = None
        self.prompt_shown = False

    def show_notification(self, message, time=5000):
        """Show a notification message"""
        xbmc.executebuiltin(f'Notification(SkipIntro,{message},{time})')
