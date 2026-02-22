import { defineCollection, z } from "astro:content";

const recipes = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    cuisine: z.string(),
    foodType: z.string().optional(),
    tags: z.array(z.string()).default([]),
    servings: z.number().int().positive().optional(),
    totalTimeMinutes: z.number().int().positive().optional(),
    image: z.string().optional(),
    ingredients: z
      .union([z.array(z.string()), z.string()])
      .transform((value) => {
        if (typeof value === "string") {
          return value
            .split(/\r?\n/)
            .map((line) => line.trim().replace(/^-+\s*/, ""))
            .filter(Boolean);
        }
        return value;
      })
      .optional(),
  }),
});

const mealPlans = defineCollection({
  type: "data",
  schema: z.object({
    weekStart: z.string(),
    days: z.record(
      z.object({
        recipeSlug: z.string().nullable(),
        notes: z.string().optional(),
      })
    ),
  }),
});

/** NEW: Meta collection for cuisines */
const meta = defineCollection({
  type: "data",
  schema: z.object({
    cuisines: z.array(
      z.object({
        slug: z.string(),
        label: z.string().optional(),
      })
    ),
  }),
});

export const collections = {
  recipes,
  "meal-plans": mealPlans,
  meta,
};
