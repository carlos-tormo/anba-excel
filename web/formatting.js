(function initAnbaFormatting(global) {
  function dateTimeEs(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  global.AnbaFormatting = {
    dateTimeEs,
  };
})(window);
