// Plain-language copy + data lists for "Tell us what you own". No state names are typed here.
export const US_STATES = ["Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut","Delaware","District of Columbia","Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts","Michigan","Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada","New Hampshire","New Jersey","New Mexico","New York","North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island","South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont","Virginia","Washington","West Virginia","Wisconsin","Wyoming"];

export const KIND_OPTIONS = [
  ["house_land", "House or Land"], ["bank", "Bank Account"], ["investment", "Investment Account"], ["vehicle", "Vehicle"],
  ["business", "Business Ownership"], ["belongings", "Personal Belongings (furniture, jewelry, art, and so on)"],
  ["life_insurance", "Life Insurance Policy"], ["cash", "Cash"], ["other", "Other"], ["unsure", "I am not sure. Please help me."],
];
export const KIND_LABEL = Object.fromEntries(KIND_OPTIONS.map(([k, l]) => [k, l.split(" (")[0]]));
export const OTHER_KINDS = ["Cryptocurrency", "Collectibles (coins, cards, antiques)", "Money Someone Owes You",
  "Royalties or Creative Work (books, music, patents)", "Equipment or Livestock", "Online Accounts or Digital Items", "Something Else"];
export const STATE_KINDS = new Set(["house_land", "vehicle"]);
export const EXAMPLES = {
  house_land: "House at 12 Oak Street, in my city", bank: "Checking account at my bank, ending in 4417",
  investment: "Brokerage account ending in 8820", vehicle: "2021 Honda Accord, last 6 of the VIN: 123456",
  business: "My 50 percent ownership of Smith Consulting LLC", belongings: "All my furniture, jewelry, and art at my home",
  life_insurance: "Life insurance policy ending in 5521", cash: "$5,000 cash",
};
export const METHOD_OTHER = "__other__";
export const METHOD_UNSURE = "__unsure__";

export const COPY = {
  intro: "Your trust is like an empty box. Whatever you put in the box belongs to the trust. Tell us what you own and what you would like to put in. Just type it the way you would tell a friend. We will help with the rest.",
  retirement: "Retirement accounts like an IRA or 401k stay in your name. Do not list them here. We will talk with you about them separately.",
  noNumbers: "Please do not type full account numbers, Social Security numbers, or passwords.",
  initials: "Your trustee will sign next to each line when you both meet to sign.",
  infoOnly: "This form collects information only. It does not replace your signed trust documents.",
  unsure: "No problem. We will help you with this step.",
  typeLabel: "In your own words, tell us what you own. List as many things as you like.",
  typeExample: "I own a house, a checking account at my bank, a 2020 truck, and half of a business.",
};

export const HELP = {
  what: "Write a few words so someone could find this item. For an account, use only the last 4 numbers.",
  kind: "Pick the group this item fits in. If you are not sure, pick \"I am not sure.\" We will help.",
  state: (s) => `Houses, land, and vehicles follow the rules of the state they are in. We filled in ${s || "your state"} from your address. Change it if the item is somewhere else.`,
  inTrust: "Tell us if you want this item in your trust. If you are not sure yet, that is okay.",
  date: "This is the day you signed the paper or finished the form. It is not the day you bought it.",
  method: "This is the paperwork that makes it official. A lawyer might call it an \"instrument.\" That just means a signed paper.",
};

export const STATUS_LABEL = { planned: "Planned", moved: "Moved into trust" };
