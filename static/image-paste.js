(function () {
  const MAX_DIMENSION = 1600;
  const JPEG_QUALITY = 0.85;

  function readAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("Could not read the pasted image."));
      reader.readAsDataURL(file);
    });
  }

  function loadImage(dataUrl) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("The pasted image format is not supported."));
      image.src = dataUrl;
    });
  }

  async function prepareImage(file) {
    const dataUrl = await readAsDataUrl(file);
    const image = await loadImage(dataUrl);
    const scale = Math.min(1, MAX_DIMENSION / Math.max(image.width, image.height));
    const width = Math.max(1, Math.round(image.width * scale));
    const height = Math.max(1, Math.round(image.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.drawImage(image, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  }

  window.enablePastedImages = function enablePastedImages(quill) {
    if (!quill || !quill.root) return;

    quill.root.addEventListener("paste", async event => {
      const files = Array.from(event.clipboardData?.items || [])
        .filter(item => item.kind === "file" && item.type.startsWith("image/"))
        .map(item => item.getAsFile())
        .filter(Boolean);

      if (!files.length) return;

      event.preventDefault();
      event.stopImmediatePropagation();

      let index = (quill.getSelection() || {}).index;
      if (typeof index !== "number") index = quill.getLength() - 1;

      for (const file of files) {
        try {
          const imageData = await prepareImage(file);
          quill.insertEmbed(index, "image", imageData, "user");
          index += 1;
          quill.setSelection(index, 0, "silent");
        } catch (error) {
          alert(error.message || "Could not paste that image.");
        }
      }
    }, true);
  };
})();
