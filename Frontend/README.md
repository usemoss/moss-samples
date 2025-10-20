<h1 align="center">
  ⚛ Simplefolio React ⚛
</h1>

<h2 align="center">
  A clean, beautiful and responsive portfolio template for developers!
</h2>

<img src="/public/simplefolio-react-preview.gif">

Feel free to use it as-is or customize it as much as you want. This template was created from scratch and inspired by [Simplefolio](https://github.com/cobidev/simplefolio) by [Jacobo Martinez](https://github.com/cobidev). 
Simplefolio React uses (roughly) the same portofolio template in React.js.

---

## Getting Started

See the instructions down below at [Installation](#installation) 
and [Running / Development](#running-/-development) to get a copy of the 
project up and running on your local machine for development and 
testing purposes.

---

## Template Instructions:

### Step 1

To update the portfolio, all details are updated in the included index.json file:  

```json
{
  "navigation": [
		{
			"title": "About",
			"url": "http://www.example.com/about"
		},
		{
			"title": "Projects",
			"url": "http://www.example.com/portfolio"
		},
		{
			"title": "Contact",
			"url": "http://www.example.com/contact"
		}
	],
  "hero": {
    "name": "Your Name",
    "subtitle": "I'm the Unknown Developer."
  },
  "about": {
    "title": "About me",
    "image": "/placeholder.png",
    "primary": "This is where you can describe about yourself. The more you describe about yourself, the more chances you have!",
    "secondary": "Extra Information about you! like hobbies and your goals."
  },
  "projects": {
    "title": "Projects",
    "projects": [
      {
        "title": "Project 1",
        "description": "Describe the project being very specific, you can use the Twitter standard: no more than 280 characters: complement the information: the skills learned or reinforced in its realization and how you faced it, prove to be proactive in the search for solutions.",
        "url": "http://www.example.com/project1",
        "github": "http://www.example.com/github",
        "image": "/placeholder-700x350.png"
      },
      {
				"title": "Project 2",
				"description": "Demonstrate in this description the skills of a programmer: such as having commitment, having perseverance and accepting alternative solutions. Remember that being a portfolio you are not selling the project, you are selling yourself, it reflects the resources used: Frameworks, libraries, platforms, etc.",
				"url": "http://www.example.com/project2",
        "github": "http://www.example.com/github",
				"image": "/placeholder-700x350.png"
			},
      {
				"title": "Project 3",
				"description": "If the project was collaborative, reflect it in this description, that will demonstrate communication and/or leadership skills. Additionally, if you made use of the mastery of a second language, it will reflect on you professionalism.",
				"url": "http://www.example.com/project3",
        "github": "http://www.example.com/github",
				"image": "/placeholder-700x350.png"
			}
    ]
  },
  "contact": {
    "title": "Contact",
    "description": "This is where you can describe about your contact. The more you describe about your contact, the more chances you have!",
    "formId": "your-form-id"
  },
  "footer": {
		"linkedin": "",
		"twitter": "",
		"github": ""
	}
}
```

### Step 2

Set up your contact account with Formspree. 

1. Go to [https://formspree.io/](https://formspree.io/).
2. Create account.
3. Get your form id. 
4. Copy/paste your form id into the formId section of the index.json file.

---

## Technologies used

- [Tailwind](https://tailwindcss.com/) - Utility-First CSS framework
- [Next.js](https://nextjs.org/) - Web development framework
- [Vite](https://vitejs.dev) - Frontend development environment
- [Formspree](https://formspree.io/) - Form processing API

## Authors

- **Dylan Arveson** - [https://github.com/dyyllaann](https://github.com/dyyllaann)

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

I was motivated to create this project after seeing the Simplefolio that [Jacobo Martinez](https://github.com/cobimr) created and shared with the [ZTM Community](https://github.com/zero-to-mastery) and [Andrei](https://github.com/aneagoie)

## Prerequisites

You will need the following things properly installed on your computer.

* [Git](https://git-scm.com/)
* [Node.js](https://nodejs.org/) (with npm)
* [Google Chrome](https://google.com/chrome/)

## Installation

* `git clone https://github.com/dyyllaann/simplefolio-react.git` this repository
* `cd simplefolio-react`
* `npm install`

## Running / Development

* `npm run dev`
* Visit your app at [http://localhost:3000](http://localhost:3000).

### Linting

* `npm run lint:hbs`
* `npm run lint:js`
* `npm run lint:js -- --fix`

### Building

*  `npm run build`