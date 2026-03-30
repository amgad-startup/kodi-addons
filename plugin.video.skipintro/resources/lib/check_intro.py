import xbmc
import xbmcaddon

# Get the running instance of our addon
addon = xbmcaddon.Addon()
xbmc.log('SkipIntro: Time check helper started', xbmc.LOGINFO)

# Send notification to trigger time check in main addon
xbmc.executebuiltin('NotifyAll(SkipIntro,TimeCheck)')
xbmc.log('SkipIntro: Sent time check notification', xbmc.LOGINFO)
