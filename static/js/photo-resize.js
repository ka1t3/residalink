// Redimensionnement des photos côté navigateur, avant l'envoi.
//
// JavaScript natif, aucune dépendance : aucune ressource externe, la CSP reste
// inchangée. Ce fichier est chargé uniquement sur les pages qui contiennent un
// champ photo (`data-photo-uploader`), jamais dans base.html.
//
// Ce n'est qu'une optimisation de transport : le serveur (core/photos.py,
// validate_photo / prepare_photo) reste la seule autorité. Si ce script
// échoue, est désactivé, ou n'est pas supporté, le formulaire envoie les
// fichiers d'origine sans se bloquer.
(function () {
  'use strict';

  var MAX_DIMENSION = 2000;   // cohérent avec core/photos.py::MAX_DIMENSION
  var JPEG_QUALITY = 0.85;

  function supported() {
    return typeof DataTransfer === 'function'
      && typeof File === 'function'
      && typeof URL !== 'undefined'
      && !!document.createElement('canvas').getContext;
  }

  function setFiles(input, files) {
    var dt = new DataTransfer();
    for (var i = 0; i < files.length; i++) dt.items.add(files[i]);
    input.files = dt.files;
  }

  // Charge l'image via <img>. Le navigateur applique l'orientation EXIF à la
  // lecture (image-orientation: from-image est le défaut CSS depuis 2020) :
  // drawImage dessine donc des pixels déjà redressés — jamais couchés ni
  // retournés. Si le fichier n'est pas décodable par le navigateur (ex. HEIC),
  // on rejette : le fichier d'origine est conservé et le serveur s'en charge.
  function loadImage(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode')); };
      img.src = url;
    });
  }

  function resize(file) {
    return loadImage(file).then(function (img) {
      var w = img.naturalWidth;
      var h = img.naturalHeight;
      if (!w || !h || Math.max(w, h) <= MAX_DIMENSION) return file;

      var scale = MAX_DIMENSION / Math.max(w, h);
      var cw = Math.round(w * scale);
      var ch = Math.round(h * scale);
      var canvas = document.createElement('canvas');
      canvas.width = cw;
      canvas.height = ch;
      var ctx = canvas.getContext('2d');
      // Fond blanc : une image transparente (PNG) ne doit pas ressortir noire.
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, cw, ch);
      ctx.drawImage(img, 0, 0, cw, ch);

      return new Promise(function (resolve, reject) {
        canvas.toBlob(function (blob) {
          if (!blob) { reject(new Error('toBlob')); return; }
          var name = file.name.replace(/\.[^.]+$/, '') || 'photo';
          resolve(new File([blob], name + '.jpg', { type: 'image/jpeg' }));
        }, 'image/jpeg', JPEG_QUALITY);
      });
    });
  }

  function totalFiles(container) {
    var n = 0;
    var inputs = container.querySelectorAll('input[type=file][name=photos]');
    for (var i = 0; i < inputs.length; i++) n += inputs[i].files.length;
    return n;
  }

  function refresh(container) {
    var el = container.querySelector('[data-photo-count]');
    if (!el) return;
    var n = totalFiles(container);
    el.textContent = n ? n + (n > 1 ? ' photos' : ' photo') : '';
  }

  function busy(container, on) {
    var status = container.querySelector('[data-photo-status]');
    if (status) status.textContent = on ? 'Préparation des photos…' : '';
    var form = container.closest('form');
    if (!form) return;
    var buttons = form.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) buttons[i].disabled = on;
  }

  function onChange(container, input) {
    if (!input.files.length) { refresh(container); return; }
    var original = Array.prototype.slice.call(input.files);
    busy(container, true);
    Promise.all(original.map(function (f) {
      return resize(f).catch(function () { return f; });
    })).then(function (files) {
      setFiles(input, files);
      refresh(container);
      busy(container, false);
    }).catch(function () {
      busy(container, false);
    });
  }

  function init() {
    if (!supported()) return;
    var containers = document.querySelectorAll('[data-photo-uploader]');
    Array.prototype.forEach.call(containers, function (container) {
      var inputs = container.querySelectorAll('input[type=file][name=photos]');
      Array.prototype.forEach.call(inputs, function (input) {
        input.addEventListener('change', function () { onChange(container, input); });
      });
      refresh(container);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
