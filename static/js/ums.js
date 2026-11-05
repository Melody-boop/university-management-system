document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('menuToggle');
  toggle?.addEventListener('click', () => sidebar?.classList.toggle('open'));
  document.addEventListener('click', (event) => {
    if (window.innerWidth <= 760 && sidebar?.classList.contains('open') && !sidebar.contains(event.target) && !toggle?.contains(event.target)) {
      sidebar.classList.remove('open');
    }
  });
  document.querySelectorAll('.password-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      const input = button.parentElement.querySelector('input');
      const visible = input.type === 'password';
      input.type = visible ? 'text' : 'password';
      button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
      button.innerHTML = `<i class="bi bi-eye${visible ? '-slash' : ''}"></i>`;
    });
  });
  document.querySelectorAll('[data-bs-dismiss="alert"]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.alert')?.remove());
  });
});