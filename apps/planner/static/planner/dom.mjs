export const rupiah = (value) => "Rp " + Number(value).toLocaleString("id-ID");

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export const csrfToken = () => document.querySelector('[name="csrfmiddlewaretoken"]').value;
