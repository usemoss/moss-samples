/** @type {import('tailwindcss').Config} */
// const plugin = require("tailwindcss/plugin");

module.exports = {
	darkMode: "class",
	content: [
		"./pages/**/*.{js,ts,jsx,tsx}",
		"./components/**/*.{js,ts,jsx,tsx}",
		"./app/**/*.{js,ts,jsx,tsx}",
	],
	theme: {
		extend: {
			keyframes: {
				marquee1: {
					"0%": { transform: "translateX(0%)" },
					"100%": { transform: "translateX(-100%)" },
				},
				marquee2: {
					"0%": { transform: "translateX(100%)" },
					"100%": { transform: "translateX(0%)" },
				},
			},
			animation: {
				marquee1: "marquee1 40s linear infinite",
				marquee2: "marquee2 40s linear infinite",
			},
			backgroundImage: {
				"gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
				"gradient-conic":
					"conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
			},
		},
	},
	plugins: [
		// plugin(function ({ addBase, theme }) {
		// 	addBase({
		// 		h1: { fontSize: theme("fontSize.2xl") },
		// 		h2: { fontSize: theme("fontSize.xl") },
		// 		h3: { fontSize: theme("fontSize.lg") },
		// 	});
		// }),
	],
};
