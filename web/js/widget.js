var foo = "Hello World!";
document.write("<p>Before our anomymous function foo means '" + foo + '".</p>');

// The following code will be enclosed into an anomymous function
(function() {
    var foo = "Goodbye World!";
    document.write("<p>Inside our anomymous function foo means '" + foo + '".</p>');
})(); // We call our anonymous function immediately

document.write("<p>After our anomymous function foo means '" + foo + '".</p>');
