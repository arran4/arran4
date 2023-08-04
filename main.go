package main

import (
	"fmt"
	"strings"
    "io/ioutil"
    "os"
)

func main() {
    fmt.Println("Path:", os.Getenv("Path"))
    fmt.Println("PathExt:", os.Getenv("PathExt"))

	pathExt = strings.Split(os.Getenv("PathExt"), string(";"))
	paths = strings.Split(os.Getenv("Path"), string(";"))

	fmt.Println("Path:", paths)
    fmt.Println("PathExt:", pathExt)

	fmt.Println("")

	for _, path := range paths {
		files, err := ioutil.ReadDir(path)
		fmt.Println("Dir: ", path)
		if err != nil {
			fmt.Println(err)
			continue
		}
	
		// Print the names of all the files.
		for _, file := range files {
			fmt.Println(file.Name())
		}
		fmt.Println("")
	
	}

}