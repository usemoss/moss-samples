import { runMetadataFilterExample } from "./shared";

runMetadataFilterExample({
  operator: "$in",
  description: "Use $in to match documents whose metadata value is in an allowed list.",
  query: "portable gear for commuters",
  filter: {
    field: "city",
    condition: { $in: ["new-york", "seattle"] },
  },
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
