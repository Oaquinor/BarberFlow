(function () {
  const installButton = document.getElementById('installAppBtn');
  const installBanner = document.getElementById('installBanner');
  const installBannerButton = document.getElementById('installBannerBtn');

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', async () => {
      try {
        await navigator.serviceWorker.register('/sw.js');
      } catch (error) {
        console.error('Service Worker registration failed:', error);
      }
    });
  }

  let deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    if (installButton) {
      installButton.style.display = 'inline-block';
    }
    if (installBanner) {
      installBanner.style.display = 'flex';
    }
  });

  window.addEventListener('appinstalled', () => {
    if (installButton) {
      installButton.style.display = 'none';
    }
    if (installBanner) {
      installBanner.style.display = 'none';
    }
    deferredPrompt = null;
  });

  window.showInstallPwaPrompt = async function () {
    if (!deferredPrompt) return false;

    deferredPrompt.prompt();
    const choiceResult = await deferredPrompt.userChoice;
    deferredPrompt = null;

    return choiceResult.outcome === 'accepted';
  };

  if (installButton) {
    installButton.addEventListener('click', async () => {
      const installed = await window.showInstallPwaPrompt();
      if (installed) {
        installButton.style.display = 'none';
      }
    });
  }

  if (installBannerButton) {
    installBannerButton.addEventListener('click', async () => {
      const installed = await window.showInstallPwaPrompt();
      if (installed && installBanner) {
        installBanner.style.display = 'none';
      }
    });
  }
})();