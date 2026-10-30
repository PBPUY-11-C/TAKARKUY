// Turn the comma-separated "bahan yang dihindari" field into removable chips with an add box.
export function initAvoidChips() {
  document.querySelectorAll("[data-avoid]").forEach((box) => {
    const field = box.querySelector('input[name="exclude_ingredients"]');
    const chips = box.querySelector("[data-avoid-chips]");
    const count = box.querySelector("[data-avoid-count]");
    if (!field || !chips) return;
    const terms = () => field.value.split(",").map((term) => term.trim()).filter(Boolean);
    const adder = document.createElement("div");
    adder.className = "avoid-add";
    const input = document.createElement("input");
    input.type = "text";
    input.id = `${field.id}-add`;
    input.placeholder = "misalnya udang";
    input.autocomplete = "off";
    const add = document.createElement("button");
    add.type = "button";
    add.className = "secondary-button";
    add.textContent = "Tambah";
    adder.append(input, add);
    field.after(adder);
    field.hidden = true;
    const label = box.querySelector(`label[for="${field.id}"]`);
    if (label) label.htmlFor = input.id;

    const render = () => {
      chips.replaceChildren(...terms().map((term) => {
        const chip = document.createElement("span");
        chip.className = "avoid-chip";
        chip.textContent = term;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.setAttribute("aria-label", `Hapus ${term}`);
        remove.addEventListener("click", () => {
          field.value = terms().filter((other) => other !== term).join(", ");
          render();
          input.focus();
        });
        chip.append(remove);
        return chip;
      }));
      count.textContent = String(terms().length);
      count.hidden = !terms().length;
    };
    const push = () => {
      const known = new Set(terms().map((term) => term.toLowerCase()));
      const added = input.value.split(",").map((term) => term.trim()).filter((term) => term && !known.has(term.toLowerCase()));
      if (added.length) field.value = [...terms(), ...added].join(", ");
      input.value = "";
      render();
      input.focus();
    };
    add.addEventListener("click", push);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); push(); }
    });
    render();
  });
}
