import { renderCart } from "./cart.js";

export function bootstrap(root) {
  root.addEventListener("click", () => renderCart(root));
  return root;
}






