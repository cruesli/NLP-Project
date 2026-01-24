import { displayFromSlug } from "./displayFromSlug";

export type CuisineItem = { slug: string; label?: string };

export function cuisineLabel(c: CuisineItem) {
  return c.label?.trim() ? c.label : displayFromSlug(c.slug);
}