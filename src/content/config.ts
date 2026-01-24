import { defineCollection, z } from "astro:content";

const recipes = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    // If you prefer filename-based slugs, you can remove this and rely on entry.slug.
    slug: z.string().optional(),
    cuisine: z.string(),           // e.g. "italian"
    foodType: z.string().optional(), // e.g. "dinner"
    tags: z.array(z.string()).default([]),
    servings: z.number().int().positive().optional(),
    totalTimeMinutes: z.number().int().positive().optional(),
    image: z.string().optional(),  // e.g. "/images/recipes/spaghetti-bolognese.jpg"
  }),
});

const mealPlans = defineCollection({
  type: "data",
  schema: z.object({
    weekStart: z.string(), // YYYY-MM-DD
    days: z.record(
      z.object({
        recipeSlug: z.string().nullable(),
        notes: z.string().optional(),
      })
    ),
  }),
});

export const collections = {
  recipes,
  "meal-plans": mealPlans,
};
