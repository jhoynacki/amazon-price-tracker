// Edit product tracking rules inline
function openEdit(upId, targetPrice, targetDiscount, notifyEmail, notifySms, notifyTelegram) {
  const modal = document.getElementById('edit-modal');
  document.getElementById('edit-up-id').value = upId;
  document.getElementById('edit-target-price').value = targetPrice;
  document.getElementById('edit-target-discount').value = targetDiscount;
  document.getElementById('edit-notify-email').checked = notifyEmail;
  document.getElementById('edit-notify-sms').checked = notifySms;
  document.getElementById('edit-notify-telegram').checked = notifyTelegram;
  // Update form action with correct ID
  document.getElementById('edit-form').setAttribute(
    'hx-put', `/amazon/products/${upId}`
  );
  htmx.process(document.getElementById('edit-form'));
  modal.classList.remove('hidden');
}

function closeEdit() {
  document.getElementById('edit-modal').classList.add('hidden');
}
